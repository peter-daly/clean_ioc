# from __future__ import annotations
from expects.matchers import Matcher


class be_same_instance_as(Matcher):
    def __init__(self, expected):
        self._expected = expected

    def _match(self, subject):
        return id(subject) == id(self._expected), []

    def _match_negated(self, subject):
        return id(subject) != id(self._expected), []


class be_type(Matcher):
    def __init__(self, expected):
        self._expected = expected

    def _match(self, subject):
        return type(subject) == self._expected, []

    def _match_negated(self, subject):
        return type(subject) != self._expected, []
