from pydantic import BaseModel


class FrozenModel(BaseModel):
    """不可变的 pydantic 基类，字段赋值后不可修改。"""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}
