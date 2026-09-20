from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class GetByIdRequest(_message.Message):
    __slots__ = ("term_id",)
    TERM_ID_FIELD_NUMBER: _ClassVar[int]
    term_id: str
    def __init__(self, term_id: _Optional[str] = ...) -> None: ...

class GetRandomRequest(_message.Message):
    __slots__ = ("excluded_ids",)
    EXCLUDED_IDS_FIELD_NUMBER: _ClassVar[int]
    excluded_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, excluded_ids: _Optional[_Iterable[str]] = ...) -> None: ...

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
