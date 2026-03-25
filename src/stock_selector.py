# -*- coding: utf-8 -*-
"""
==================================
股票选股模块 (Stock Selector)
==================================

根据选股规则每日筛选符合条件的股票：
1. 3% < 涨幅 < 5%
2. 量比 > 1
3. 5% < 换手率 < 10%
4. 50亿 < 市值 < 200亿
5. 成交量持续放大
6. 短期均线搭配60日线向上
7. 分时图比大盘强
"""

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from data_provider.akshare_fetcher import AkshareFetcher

logger = logging.getLogger(__name__)

SELECTION_RULE_FILE = "SelectionRule.md"
MY_STOCK_LIST_FILE = "MyStockList.md"


@dataclass
class SelectedStock:
    """选中的股票"""
    code: str
    name: str
    change_pct: float
    volume_ratio: float
    turnover_rate: float
    market_cap: float
    reason: str


class StockSelector:
    """股票选择器"""

    def __init__(self):
        self.fetcher = AkshareFetcher()
        self.results: List[SelectedStock] = []

    def select_stocks(self) -> List[SelectedStock]:
        """
        根据选股规则筛选股票
        
        Returns:
            符合条件的股票列表
        """
        logger.info("开始选股筛选...")
        
        try:
            df = self._get_all_a_stocks()
            if df.empty:
                logger.warning("未获取到A股列表")
                return []
            
            logger.info(f"获取到 {len(df)} 只A股，开始筛选...")
            
            selected = self._apply_rules(df)
            self.results = selected
            
            logger.info(f"筛选完成，共选出 {len(selected)} 只股票")
            return selected
            
        except Exception as e:
            logger.exception(f"选股失败: {e}")
            return []

    def _get_all_a_stocks(self) -> pd.DataFrame:
        """获取全部A股实时行情"""
        import akshare as ak
        
        logger.info("[API调用] 获取A股实时行情...")
        
        @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=3, max=10))
        def _fetch():
            return ak.stock_zh_a_spot_em()
        
        df = _fetch()
        return df

    def _apply_rules(self, df: pd.DataFrame) -> List[SelectedStock]:
        """
        应用选股规则筛选股票
        
        规则:
        1. 3% < 涨幅 < 5%
        2. 量比 > 1
        3. 5% < 换手率 < 10%
        4. 50亿 < 市值 < 200亿
        5. 成交量持续放大（近期成交量上升）
        6. 短期均线搭配60日线向上
        7. 分时图比大盘强
        """
        selected: List[SelectedStock] = []
        
        # 获取列名映射（akshare 返回的列名可能变化）
        col_map = self._get_column_map(df)
        
        # 规则1-4: 实时数据筛选
        df_filtered = df.copy()
        
        # 涨幅: 3% < 涨幅 < 5%
        change_col = col_map.get("涨跌幅")
        if change_col and change_col in df_filtered.columns:
            df_filtered = df_filtered[
                (df_filtered[change_col] > 3) & 
                (df_filtered[change_col] < 5)
            ]
            logger.info(f"规则1(涨幅3-5%): 剩余 {len(df_filtered)} 只")
        
        # 量比 > 1
        volume_ratio_col = col_map.get("量比")
        if volume_ratio_col and volume_ratio_col in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[volume_ratio_col] > 1]
            logger.info(f"规则2(量比>1): 剩余 {len(df_filtered)} 只")
        
        # 换手率: 5% < 换手率 < 10%
        turnover_col = col_map.get("换手率")
        if turnover_col and turnover_col in df_filtered.columns:
            df_filtered = df_filtered[
                (df_filtered[turnover_col] > 5) & 
                (df_filtered[turnover_col] < 10)
            ]
            logger.info(f"规则3(换手率5-10%): 剩余 {len(df_filtered)} 只")
        
        # 市值: 50亿 < 市值 < 200亿
        cap_col = col_map.get("总市值")
        if cap_col and cap_col in df_filtered.columns:
            # 市值单位通常是"亿"
            df_filtered = df_filtered[
                (df_filtered[cap_col] > 50) & 
                (df_filtered[cap_col] < 200)
            ]
            logger.info(f"规则4(市值50-200亿): 剩余 {len(df_filtered)} 只")
        
        # 规则5-7: 需要历史数据检查
        for _, row in df_filtered.iterrows():
            code = str(row.get(col_map.get("代码", "代码"), ""))
            name = str(row.get(col_map.get("名称", "名称"), ""))
            
            if not code:
                continue
            
            reasons = []
            
            # 规则5: 成交量持续放大
            if self._check_volume_increasing(code):
                reasons.append("成交量放大")
            
            # 规则6: 短期均线搭配60日线向上
            if self._check_ma_trend(code):
                reasons.append("均线向上")
            
            # 规则7: 分时图比大盘强
            if self._check_strength_vs_market(code):
                reasons.append("强于大盘")
            
            if reasons:
                change_pct = row.get(change_col, 0) if change_col else 0
                volume_ratio = row.get(volume_ratio_col, 0) if volume_ratio_col else 0
                turnover_rate = row.get(turnover_col, 0) if turnover_col else 0
                market_cap = row.get(cap_col, 0) if cap_col else 0
                
                selected.append(SelectedStock(
                    code=code,
                    name=name,
                    change_pct=float(change_pct),
                    volume_ratio=float(volume_ratio),
                    turnover_rate=float(turnover_rate),
                    market_cap=float(market_cap),
                    reason=",".join(reasons)
                ))
        
        logger.info(f"规则5-7筛选后: 最终选出 {len(selected)} 只股票")
        return selected[:50]  # 最多返回50只

    def _get_column_map(self, df: pd.DataFrame) -> dict:
        """获取列名映射（兼容不同版本的akshare列名）"""
        cols = df.columns.tolist()
        
        mapping = {
            "代码": None,
            "名称": None,
            "涨跌幅": None,
            "量比": None,
            "换手率": None,
            "总市值": None,
        }
        
        for col in cols:
            col_lower = col.lower()
            if "代码" in col or col_lower == "code":
                mapping["代码"] = col
            elif "名称" in col or col_lower == "name":
                mapping["名称"] = col
            elif "涨跌幅" in col or "涨幅" in col or col_lower in ["pct", "change"]:
                mapping["涨跌幅"] = col
            elif "量比" in col or col_lower == "volume_ratio":
                mapping["量比"] = col
            elif "换手率" in col or "换手" in col or col_lower in ["turnover", "turnover_rate"]:
                mapping["换手率"] = col
            elif "市值" in col or "cap" in col_lower:
                mapping["总市值"] = col
        
        return mapping

    def _check_volume_increasing(self, stock_code: str) -> bool:
        """检查成交量是否持续放大"""
        try:
            import akshare as ak
            
            # 获取近5日成交量
            end_date = datetime.now().strftime("%Y%m%d")
            df = ak.stock_zh_a_hist_em(
                symbol=stock_code,
                period="daily",
                start_date="20250101",
                end_date=end_date,
                adjust="qfq"
            )
            
            if df is None or len(df) < 5:
                return False
            
            # 简单判断：最近3天成交量大于前3天
            recent = df["成交量"].tail(3).mean()
            earlier = df["成交量"].iloc[:-3].mean() if len(df) > 3 else 0
            
            return recent > earlier * 1.2
            
        except Exception as e:
            logger.debug(f"检查成交量失败 {stock_code}: {e}")
            return False

    def _check_ma_trend(self, stock_code: str) -> bool:
        """检查短期均线和60日线趋势"""
        try:
            import akshare as ak
            
            end_date = datetime.now().strftime("%Y%m%d")
            df = ak.stock_zh_a_hist_em(
                symbol=stock_code,
                period="daily",
                start_date="20250101",
                end_date=end_date,
                adjust="qfq"
            )
            
            if df is None or len(df) < 60:
                return False
            
            # 检查60日线向上
            ma60_now = df["收盘"].iloc[-1]
            ma60_20d_ago = df["收盘"].iloc[-20] if len(df) >= 20 else df["收盘"].iloc[0]
            
            if ma60_now <= ma60_20d_ago:
                return False
            
            # 检查短期均线(5日,10日)向上
            ma5_now = df["收盘"].tail(5).mean()
            ma5_5d_ago = df["收盘"].iloc[-10:].mean() if len(df) >= 10 else df["收盘"].mean()
            
            return ma5_now > ma5_5d_ago
            
        except Exception as e:
            logger.debug(f"检查均线失败 {stock_code}: {e}")
            return False

    def _check_strength_vs_market(self, stock_code: str) -> bool:
        """检查分时图是否比大盘强"""
        try:
            import akshare as ak
            
            # 获取上证指数对比
            today = datetime.now().strftime("%Y%m%d")
            
            # 尝试获取上证指数数据
            try:
                index_df = ak.index_zh_a_hist(
                    symbol="000001",
                    period="daily",
                    start_date="20250101",
                    end_date=today
                )
                market_change = index_df["涨跌幅"].iloc[-1] if index_df is not None and len(index_df) > 0 else 0
            except:
                market_change = 0
            
            # 获取个股今日涨跌幅
            quote = self.fetcher.get_realtime_quote(stock_code)
            if quote is None:
                return False
            
            # 个股涨幅大于大盘涨幅则视为强于大盘
            return quote.change_pct > market_change + 0.5
            
        except Exception as e:
            logger.debug(f"检查相对强度失败 {stock_code}: {e}")
            return False

    def save_to_file(self, filepath: str = MY_STOCK_LIST_FILE) -> bool:
        """
        选股结果保存到文件
        
        Args:
            filepath: 输出文件路径
            
        Returns:
            是否保存成功
        """
        if not self.results:
            logger.warning("选股结果为空，不保存文件")
            return False
        
        try:
            content = [
                "# 自选股列表 (MyStockList)",
                "",
                f"更新日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "## 选股结果",
                "",
                "| 代码 | 名称 | 涨幅% | 量比 | 换手率% | 市值(亿) | 入选原因 |",
                "|------|------|-------|------|---------|----------|----------|",
            ]
            
            for stock in self.results:
                content.append(
                    f"| {stock.code} | {stock.name} | {stock.change_pct:.2f} | "
                    f"{stock.volume_ratio:.2f} | {stock.turnover_rate:.2f} | "
                    f"{stock.market_cap:.0f} | {stock.reason} |"
                )
            
            content.extend([
                "",
                "## 选股规则",
                "",
                f"见 [{SELECTION_RULE_FILE}](./{SELECTION_RULE_FILE})"
            ])
            
            Path(filepath).write_text("\n".join(content), encoding="utf-8")
            logger.info(f"选股结果已保存到 {filepath}")
            return True
            
        except Exception as e:
            logger.exception(f"保存选股结果失败: {e}")
            return False

    def get_stock_codes(self) -> str:
        """
        获取选股结果中的股票代码列表（逗号分隔）
        
        Returns:
            股票代码字符串，如 "600519,000001"
        """
        if not self.results:
            return ""
        
        return ",".join(stock.code for stock in self.results)


def run_daily_selection() -> str:
    """
    执行每日选股任务
    
    Returns:
        选中的股票代码列表（逗号分隔）
    """
    selector = StockSelector()
    results = selector.select_stocks()
    
    if results:
        selector.save_to_file()
        return selector.get_stock_codes()
    
    return ""


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    )
    
    print("开始执行每日选股任务...")
    stock_codes = run_daily_selection()
    
    if stock_codes:
        print(f"选股完成，选出股票: {stock_codes}")
    else:
        print("未选出符合条件的股票")