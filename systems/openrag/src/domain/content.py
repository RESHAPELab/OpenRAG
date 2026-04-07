from typing import TypeAlias
from uuid import uuid4

from langchain_core.documents import Document as _LangchainDocument
from pydantic import BaseModel


class Content(_LangchainDocument):
    @classmethod
    def from_document(
        cls,
        document: _LangchainDocument,
        *,
        project: str,
        source: str,
        id: str | None = None,
    ) -> "Content":
        document_dict = document.model_dump()
        document_dict["metadata"] = dict(document_dict.get("metadata", {}))
        document_dict["metadata"].update(
            {
                "project": project,
                "source": source,
                "id": id or uuid4().hex,
            }
        )
        return cls.model_validate(document_dict)


ContentFormat: TypeAlias = str


class ConvertionOptions(BaseModel):
    input_format: ContentFormat
    output_format: ContentFormat

    @property
    def is_same_format(self) -> bool:
        return self.input_format == self.output_format
