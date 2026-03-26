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
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd

from data_provider.tushare_fetcher import TushareFetcher

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
        self.fetcher = TushareFetcher()
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
            if df is None or df.empty:
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
        logger.info("[API调用] 获取A股实时行情...")
        
        try:
            # 使用 Tushare 的 stock_basic 获取股票列表
            stock_list = self.fetcher.get_stock_list()
            if stock_list is None or stock_list.empty:
                logger.warning("Tushare 获取股票列表失败")
                return pd.DataFrame()
            
            # 获取实时行情（需要逐个获取或使用其他接口）
            # 这里我们用 Tushare 的 daily 接口获取最近交易日数据
            # 然后获取前几天的数据来计算各项指标
            
            # 获取最近 5 个交易日的数据
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
            
            # 收集所有股票的实时数据
            all_quotes = []
            
            # 获取所有A股股票代码
            codes_ = stock_list['code'].tolist()
            logger.info(f"总股票数 {len(codes_)}")
            logger.info(f"所有股票代码为： {codes_}")

            """
            股票代码编码规律
            ‌沪A（上海证券交易所）‌

            ‌主板A股‌：以 ‌600、601、603、605‌ 开头
            （如：600519 贵州茅台）
            ‌科创板A股‌：以 ‌688‌ 开头
            （如：688981 中芯国际）
            ‌B股‌：以 ‌900‌ 开头

            ‌深A（深圳证券交易所）‌
            ‌主板A股‌：以 ‌000、001、002、003‌ 开头
            （如：000001 平安银行）
            ‌创业板A股‌：以 ‌300、301‌ 开头
            （如：300750 宁德时代）
            ‌B股‌：以 ‌200‌ 开头
            """
            codes = []
            for code in codes_:
                if code.startswith(('600', '601', '603', '605')):
                    codes.append(code)

            logger.info(f"开始获取 {len(codes)} 只股票的实时数据...")
            
            for i, code in enumerate(codes):
                try:
                    # 获取最近几天的日线数据
                    daily_data = self.fetcher.get_daily_data(
                        code, 
                        start_date=start_date, 
                        end_date=end_date
                    )
                    
                    if daily_data is None or daily_data.empty:
                        continue
                    
                    # 取最新一天的数据
                    latest = daily_data.iloc[0]
                    prev_day = daily_data.iloc[1] if len(daily_data) > 1 else None
                    
                    # 计算涨跌幅
                    change_pct = float(latest.get('pct_chg', 0) or 0)
                    
                    # 计算量比（今日成交量/昨日成交量）
                    volume_ratio = 1.0
                    if prev_day is not None and prev_day.get('vol', 0):
                        volume_ratio = latest.get('vol', 0) / prev_day.get('vol', 1)
                    
                    # 换手率（需要用成交量/流通股本）
                    # 这里用 amount/总市值 近似
                    turnover_rate = 0.0
                    if latest.get('amount') and latest.get('total_mv'):
                        turnover_rate = (latest.get('amount', 0) / latest.get('total_mv', 1)) * 100
                    
                    # 市值（单位：亿）
                    market_cap = float(latest.get('total_mv', 0) or 0) / 10000  # 转为亿
                    
                    all_quotes.append({
                        'code': code,
                        'name': latest.get('name', code),
                        'change_pct': change_pct,
                        'volume_ratio': volume_ratio,
                        'turnover_rate': turnover_rate,
                        'market_cap': market_cap,
                    })
                    
                    if (i + 1) % 50 == 0:
                        logger.info(f"已处理 {i + 1}/{len(codes)} 只股票")
                        
                except Exception as e:
                    logger.debug(f"获取 {code} 数据失败: {e}")
                    continue
            
            logger.info(f"成功获取 {len(all_quotes)} 只股票数据")
            return pd.DataFrame(all_quotes)
            
        except Exception as e:
            logger.exception(f"获取A股数据失败: {e}")
            return pd.DataFrame()

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
        
        # 规则1-4: 实时数据筛选
        df_filtered = df.copy()
        
        logger.info(f"df_filtered columns: {df_filtered.columns}")
        for col in df_filtered.columns:
            logger.info(f"df_filtered {col}:  {df_filtered[col]}")

        # 涨幅: 3% < 涨幅 < 5%
        if 'change_pct' in df_filtered.columns:
            df_filtered = df_filtered[
                (df_filtered['change_pct'] > 3) & 
                (df_filtered['change_pct'] < 5)
            ]
            logger.info(f"规则1(涨幅3-5%): 剩余 {len(df_filtered)} 只")

        # 量比 > 1
        if 'volume_ratio' in df_filtered.columns:    
            df_filtered = df_filtered[df_filtered['volume_ratio'] > 1]
            logger.info(f"规则2(量比>1): 剩余 {len(df_filtered)} 只")
        
        # 换手率: 5% < 换手率 < 10%
        if 'turnover_rate' in df_filtered.columns:
            df_filtered = df_filtered[
                (df_filtered['turnover_rate'] > 5) & 
                (df_filtered['turnover_rate'] < 10)
            ]
            logger.info(f"规则3(换手率5-10%): 剩余 {len(df_filtered)} 只")
        
        # 市值: 50亿 < 市值 < 200亿
        if 'market_cap' in df_filtered.columns:
            df_filtered = df_filtered[
                (df_filtered['market_cap'] > 50) & 
                (df_filtered['market_cap'] < 200)
            ]
            logger.info(f"规则4(市值50-200亿): 剩余 {len(df_filtered)} 只")
        
        # 规则5-7: 需要历史数据检查
        for _, row in df_filtered.iterrows():
            code = str(row.get("code", ""))
            name = str(row.get("name", ""))
            
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
                selected.append(SelectedStock(
                    code=code,
                    name=name,
                    change_pct=float(row.get("change_pct", 0)),
                    volume_ratio=float(row.get("volume_ratio", 0)),
                    turnover_rate=float(row.get("turnover_rate", 0)),
                    market_cap=float(row.get("market_cap", 0)),
                    reason=",".join(reasons)
                ))
        
        logger.info(f"规则5-7筛选后: 最终选出 {len(selected)} 只股票")
        return selected[:50]  # 最多返回50只

    def _check_volume_increasing(self, stock_code: str) -> bool:
        """检查成交量是否持续放大（使用Tushare）"""
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=20)).strftime('%Y%m%d')
            
            daily_data = self.fetcher.get_daily_data(
                stock_code, 
                start_date=start_date, 
                end_date=end_date
            )
            
            if daily_data is None or len(daily_data) < 5:
                return False
            
            # 简单判断：最近3天成交量大于前3天
            recent = daily_data['vol'].tail(3).mean()
            earlier = daily_data['vol'].iloc[:-3].mean() if len(daily_data) > 3 else 0
            
            return recent > earlier * 1.2
            
        except Exception as e:
            logger.debug(f"检查成交量失败 {stock_code}: {e}")
            return False

    def _check_ma_trend(self, stock_code: str) -> bool:
        """检查短期均线和60日线趋势（使用Tushare）"""
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
            
            daily_data = self.fetcher.get_daily_data(
                stock_code, 
                start_date=start_date, 
                end_date=end_date
            )
            
            if daily_data is None or len(daily_data) < 60:
                return False
            
            # 检查60日线向上
            latest_close = daily_data['close'].iloc[-1]
            ma60_20d_ago = daily_data['close'].iloc[-20] if len(daily_data) >= 20 else daily_data['close'].iloc[0]
            
            if latest_close <= ma60_20d_ago:
                return False
            
            # 检查短期均线(5日,10日)向上
            ma5_now = daily_data['close'].tail(5).mean()
            ma5_5d_ago = daily_data['close'].iloc[-10:].mean() if len(daily_data) >= 10 else daily_data['close'].mean()
            
            return ma5_now > ma5_5d_ago
            
        except Exception as e:
            logger.debug(f"检查均线失败 {stock_code}: {e}")
            return False

    def _check_strength_vs_market(self, stock_code: str) -> bool:
        """检查分时图是否比大盘强（使用Tushare）"""
        try:
            # 获取上证指数数据
            market_change = 0.0
            try:
                index_data = self.fetcher.get_daily_data(
                    "000001",
                    start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
                    end_date=datetime.now().strftime('%Y%m%d')
                )
                if index_data is not None and len(index_data) > 0:
                    market_change = float(index_data['pct_chg'].iloc[-1] or 0)
            except Exception as e:
                logger.debug(f"获取上证指数失败: {e}")
            
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