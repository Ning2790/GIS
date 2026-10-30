"""files 模块 schema（P2 资质文件上传）。"""

from pydantic import BaseModel


class FilePublic(BaseModel):
    """文件元数据。url 为平台的受控读取地址（非对象存储直链）。

    thumbnail_url：缩略图地址（列表页用），无缩略图时为 None（前端回退 url）；
    original_size：上传原始字节数（图片被压缩时与 size 对比可见压缩效果）。
    """

    id: int
    filename: str
    content_type: str
    size: int
    original_size: int | None = None
    is_public: bool = False
    url: str
    thumbnail_url: str | None = None
