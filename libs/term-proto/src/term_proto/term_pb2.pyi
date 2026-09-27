from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetByIdRequest(_message.Message):
    __slots__ = ("term_id",)
    TERM_ID_FIELD_NUMBER: _ClassVar[int]
    term_id: str
    def __init__(self, term_id: _Optional[str] = ...) -> None: ...

class GetRandomRequest(_message.Message):
    __slots__ = ("excluded_ids", "category", "min_difficulty", "require_examples", "min_definition_length")
    EXCLUDED_IDS_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    MIN_DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    REQUIRE_EXAMPLES_FIELD_NUMBER: _ClassVar[int]
    MIN_DEFINITION_LENGTH_FIELD_NUMBER: _ClassVar[int]
    excluded_ids: _containers.RepeatedScalarFieldContainer[str]
    category: str
    min_difficulty: int
    require_examples: bool
    min_definition_length: int
    def __init__(self, excluded_ids: _Optional[_Iterable[str]] = ..., category: _Optional[str] = ..., min_difficulty: _Optional[int] = ..., require_examples: _Optional[bool] = ..., min_definition_length: _Optional[int] = ...) -> None: ...

class ListCategoriesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListCategoriesReply(_message.Message):
    __slots__ = ("categories",)
    CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    categories: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, categories: _Optional[_Iterable[str]] = ...) -> None: ...

class ListTermIdsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListTermIdsReply(_message.Message):
    __slots__ = ("term_ids",)
    TERM_IDS_FIELD_NUMBER: _ClassVar[int]
    term_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, term_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class TermReply(_message.Message):
    __slots__ = ("found", "id", "term", "expansion", "definitions", "aliases", "categories", "difficulty", "examples", "related", "prerequisites", "common_mistakes")
    FOUND_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TERM_FIELD_NUMBER: _ClassVar[int]
    EXPANSION_FIELD_NUMBER: _ClassVar[int]
    DEFINITIONS_FIELD_NUMBER: _ClassVar[int]
    ALIASES_FIELD_NUMBER: _ClassVar[int]
    CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    EXAMPLES_FIELD_NUMBER: _ClassVar[int]
    RELATED_FIELD_NUMBER: _ClassVar[int]
    PREREQUISITES_FIELD_NUMBER: _ClassVar[int]
    COMMON_MISTAKES_FIELD_NUMBER: _ClassVar[int]
    found: bool
    id: str
    term: str
    expansion: str
    definitions: _containers.RepeatedScalarFieldContainer[str]
    aliases: _containers.RepeatedScalarFieldContainer[str]
    categories: _containers.RepeatedScalarFieldContainer[str]
    difficulty: int
    examples: _containers.RepeatedScalarFieldContainer[str]
    related: _containers.RepeatedScalarFieldContainer[str]
    prerequisites: _containers.RepeatedScalarFieldContainer[str]
    common_mistakes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, found: _Optional[bool] = ..., id: _Optional[str] = ..., term: _Optional[str] = ..., expansion: _Optional[str] = ..., definitions: _Optional[_Iterable[str]] = ..., aliases: _Optional[_Iterable[str]] = ..., categories: _Optional[_Iterable[str]] = ..., difficulty: _Optional[int] = ..., examples: _Optional[_Iterable[str]] = ..., related: _Optional[_Iterable[str]] = ..., prerequisites: _Optional[_Iterable[str]] = ..., common_mistakes: _Optional[_Iterable[str]] = ...) -> None: ...

class SearchChunksRequest(_message.Message):
    __slots__ = ("query", "top_k")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    TOP_K_FIELD_NUMBER: _ClassVar[int]
    query: str
    top_k: int
    def __init__(self, query: _Optional[str] = ..., top_k: _Optional[int] = ...) -> None: ...

class SearchChunksReply(_message.Message):
    __slots__ = ("chunks",)
    CHUNKS_FIELD_NUMBER: _ClassVar[int]
    chunks: _containers.RepeatedCompositeFieldContainer[DocumentChunkResult]
    def __init__(self, chunks: _Optional[_Iterable[_Union[DocumentChunkResult, _Mapping]]] = ...) -> None: ...

class DocumentChunkResult(_message.Message):
    __slots__ = ("text", "source_file")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FILE_FIELD_NUMBER: _ClassVar[int]
    text: str
    source_file: str
    def __init__(self, text: _Optional[str] = ..., source_file: _Optional[str] = ...) -> None: ...
