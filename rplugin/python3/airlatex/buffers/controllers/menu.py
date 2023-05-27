from collections import namedtuple
from typing import List, Union, Dict
import inspect
from copy import deepcopy

import textwrap

from airlatex.lib.task import AsyncDecorator


class Menu():

  def __init__(self, title=None, size=80, actions=None):
    if not title:
      title = ""
    if actions is None:
      actions = {}
    self.Item = _make_menu_item(actions)
    self.entries = []
    self._handlers = {}
    self.clear(title, size)

  def clear(self, title, size):
    self.title = title
    self.size = size
    self.previous = deepcopy(self.entries)
    self.entries = [(self.title.center(self.size).rstrip(), None), ("", None)]
    self.entries_by_key = {}
    return self

  def add_entry(self, line, action=None, key=None, indent=0):
    if key:
      self.entries_by_key[key] = len(self.entries)
    self.entries.append(((" " * indent) + line, action))

  def add_blob(self, blob, action=None, key=None, indent=0):
    for line in blob.split("\n"):
      self.add_entry(line, action=action, key=key, indent=indent)

  def add_bulk(self, *lines):
    for line in lines:
      self.add_entry(*line)

  def from_dictionary(self, keys, data):
    lines = []
    for key_format_item in keys:
      if not isinstance(key_format_item, tuple):
        raise Exception("Error, expected tuple")
      key, format, item = "", "", None
      if len(key_format_item) == 3:
        key, format, item = key_format_item
      if len(key_format_item) == 2:
        key, format = key_format_item
      if len(key_format_item) == 1:
        key = ""
        format, = key_format_item

      if isinstance(key, tuple):
        lookup = tuple((data.get(k, "") for k in key))
      else:
        lookup = data.get(key, "")
      if isinstance(lookup, dict):
        line = format.format(**lookup)
      elif isinstance(lookup, tuple):
        line = format.format(*lookup)
      else:
        line = format.format(lookup)
      lines.append((line, item, key))
    return self.add_bulk(*lines)

  def space(self, n):
    for _ in range(n):
      self.add_entry('')

  @AsyncDecorator
  def updateEntryByKey(self, key, line):
    _, action = self.entries[self.entries_by_key[key]]
    self.entries[self.entries_by_key[key]] = (line, action)

  def add_block(self, content, headers=None):
    if len(headers) != 2:
      raise Exception("You can implement this in a PR if you want")
    size = self.size
    user, short_date = headers

    space = size - len(user) - len(short_date) - 6
    user = f"  {user} │"
    self.add_entry(f"¶{user} {' ' * space}{short_date}")
    self.add_entry(
        "┌" + '─' * (len(user) - 1) + '┴' + '─' * (size - 2 - len(user)) + "┐")
    for line in textwrap.wrap(content, width=size - 3):
      self.add_entry(f'│  {line}')
    self.add_entry('└')
    self.add_entry('')

  def handle(self, actionClass, key="enter"):

    def decorator(fn):
      self._handlers[(actionClass, key)] = fn
      return fn

    return decorator


class MenuItem:
  """Menu Item"""


def _make_menu_item(data: Dict[str, Union[List[str], Dict[str, List[str]]]]):
  menu_classes = {}

  # Create namedtuples from the Enum
  def generateParentClass(name, fields):
    return type(
        name, (MenuItem,), {field: menu_classes[field] for field in fields})

  def generateDataClass(name, fields):
    return type(name, (MenuItem, namedtuple(name, fields)), {})

  def build_class(name, root):
    # Recurse down first to build all the data classes
    for field, value in root.items():
      if isinstance(value, dict):
        build_class(field, value)

    for field, value in root.items():
      if isinstance(value, list):
        menu_classes[field] = generateDataClass(field, value)

    menu_classes[name] = generateParentClass(name, list(root.keys()))
    return menu_classes[name]

  return build_class("Item", data)
