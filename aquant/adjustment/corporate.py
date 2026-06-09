from __future__ import annotations

from datetime import date

from pydantic import Field

from aquant.core.pydantic_base import FrozenModel


class CashDividend(FrozenModel):
    """现金分红。

    在 pay_date 当日，框架将税后红利按持股数打入现金，并降低持仓成本基础。
    """

    symbol: str = Field(description="标的代码。")
    register_date: date = Field(description="股权登记日。收盘时持有该股票才有资格获得本次分红。")
    pay_date: date = Field(description="现金红利到账日，框架在此日期处理分红。")
    amount_per_share: float = Field(gt=0, description="税后现金红利（元/股）。例：每股派 0.5 元则填 0.5。")


class BonusShares(FrozenModel):
    """送股（股票股利）。

    在 ex_date 当日，框架按持股数增加仓位，成本基础摊薄。
    新增份额当日不可卖出（T+1）。
    """

    symbol: str = Field(description="标的代码。")
    register_date: date = Field(description="股权登记日。收盘时持有该股票才有资格获得本次送股。")
    ex_date: date = Field(description="除权日，框架在此日期增加持仓股数。")
    ratio: float = Field(gt=0, description="送股比例。例：每股送 0.3 股则填 0.3，持有 1000 股将增加 300 股。")


class RightsIssue(FrozenModel):
    """配股。

    持股人有权以低于市价的 price_per_share 认购新股，不认购则权益被稀释。
    框架记录配股事件但不自动处理认购（需要持股人主动出资）。
    策略可在 on_bar 里通过查询数据源自行决定是否参与配股。
    """

    symbol: str = Field(description="标的代码。")
    register_date: date = Field(description="股权登记日。收盘时持有该股票才有资格参与本次配股。")
    ex_date: date = Field(description="除权日。")
    ratio: float = Field(gt=0, description="配股比例。例：每股配 0.3 股则填 0.3。")
    price_per_share: float = Field(gt=0, description="配股价格（元/股），通常低于当前市价。")


# 企业行动的 Union 类型，DataSource.load_adjustments 返回此类型的列表
CorporateAction = CashDividend | BonusShares | RightsIssue
