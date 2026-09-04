// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title TwoPoolArb — capital-free atomic arbitrage between two concentrated-liquidity pools of the same pair
/// (Uniswap V3, PancakeSwap V3, Aerodrome/Velodrome Slipstream). Works as a nested flash swap:
///   1. swap on poolSell (exact input `amountIn` of tokenIn) -> the pool sends tokenOut to us first, then calls back;
///   2. inside that callback we buy exactly `amountIn` of tokenIn on poolBuy (exact output), paying with the tokenOut
///      we just received (poolBuy's callback), and hand tokenIn to poolSell.
/// Profit = tokenOut received - tokenOut paid, kept in the contract. No inventory, no flash-loan fee.
interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address a) external view returns (uint256);
}
interface IV3Pool {
    function swap(address recipient, bool zeroForOne, int256 amountSpecified, uint160 sqrtPriceLimitX96, bytes calldata data)
        external returns (int256 amount0, int256 amount1);
    function token0() external view returns (address);
    function token1() external view returns (address);
}

contract TwoPoolArb {
    address public owner;          // slot 0
    address private activePool;    // slot 1: the only pool allowed to call back right now
    uint160 private constant MIN_SQRT = 4295128740;
    uint160 private constant MAX_SQRT = 1461446703485210103287273052203988822378723970341;

    struct Params {
        address poolSell;      // pool where tokenIn is sold (its price of tokenIn is the higher one)
        address poolBuy;       // pool where tokenIn is bought back
        bool zeroForOneSell;   // direction on poolSell (true: sell token0)
        uint256 amountIn;      // exact input on poolSell
        uint256 minOutSell;    // early exit: revert if poolSell pays less than this (someone moved it first)
        uint160 limitSell;     // sqrt price limit on poolSell (0 = none)
        uint160 limitBuy;      // sqrt price limit on poolBuy (0 = none)
        int256 minProfit;      // in tokenOut units; may be negative for dry tests
    }

    event Arb(address indexed poolSell, address indexed poolBuy, bool zeroForOneSell, uint256 amountIn, int256 profit);

    constructor() { owner = msg.sender; }
    modifier onlyOwner() { require(msg.sender == owner, "owner"); _; }

    function execute(Params calldata p) external onlyOwner returns (int256 profit) {
        IV3Pool sell = IV3Pool(p.poolSell);
        address tokenOut = p.zeroForOneSell ? sell.token1() : sell.token0();
        uint256 before = IERC20(tokenOut).balanceOf(address(this));
        activePool = p.poolSell;
        sell.swap(address(this), p.zeroForOneSell, int256(p.amountIn),
                  p.limitSell != 0 ? p.limitSell : (p.zeroForOneSell ? MIN_SQRT : MAX_SQRT), abi.encode(p));
        activePool = address(0);
        profit = int256(IERC20(tokenOut).balanceOf(address(this))) - int256(before);
        require(profit >= p.minProfit, "profit");
        emit Arb(p.poolSell, p.poolBuy, p.zeroForOneSell, p.amountIn, profit);
    }

    // Uniswap V3 and Slipstream use this name; PancakeSwap V3 uses pancakeV3SwapCallback. Same semantics:
    // positive delta = amount we owe the pool, negative = amount the pool already sent us.
    function uniswapV3SwapCallback(int256 a0, int256 a1, bytes calldata data) external { _callback(a0, a1, data); }
    function pancakeV3SwapCallback(int256 a0, int256 a1, bytes calldata data) external { _callback(a0, a1, data); }

    function _callback(int256 a0, int256 a1, bytes calldata data) internal {
        require(msg.sender == activePool, "pool");
        Params memory p = abi.decode(data, (Params));
        if (msg.sender == p.poolSell) {
            uint256 owed = uint256(p.zeroForOneSell ? a0 : a1);       // tokenIn we must return to poolSell
            uint256 got  = uint256(-(p.zeroForOneSell ? a1 : a0));    // tokenOut already received
            require(got >= p.minOutSell, "minOut");                   // cheap early exit when beaten
            IV3Pool sell = IV3Pool(p.poolSell);
            address tokenIn = p.zeroForOneSell ? sell.token0() : sell.token1();
            bool dirBuy = !p.zeroForOneSell;                          // buy tokenIn on poolBuy = opposite direction
            activePool = p.poolBuy;
            IV3Pool(p.poolBuy).swap(address(this), dirBuy, -int256(owed),
                                    p.limitBuy != 0 ? p.limitBuy : (dirBuy ? MIN_SQRT : MAX_SQRT), data);
            activePool = p.poolSell;
            require(IERC20(tokenIn).transfer(p.poolSell, owed), "pay sell");
        } else {
            // poolBuy callback: pay tokenOut for the exact-output purchase
            bool dirBuy = !p.zeroForOneSell;
            uint256 owed = uint256(dirBuy ? a0 : a1);
            IV3Pool sell = IV3Pool(p.poolSell);
            address tokenOut = p.zeroForOneSell ? sell.token1() : sell.token0();
            require(IERC20(tokenOut).transfer(p.poolBuy, owed), "pay buy");
        }
    }

    function withdraw(address token, uint256 amount) external onlyOwner { require(IERC20(token).transfer(owner, amount), "xfer"); }
    function withdrawETH() external onlyOwner { (bool ok,) = owner.call{value: address(this).balance}(""); require(ok, "eth"); }
    receive() external payable {}
}
