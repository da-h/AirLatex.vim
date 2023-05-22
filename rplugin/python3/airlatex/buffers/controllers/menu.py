from collections import namedtuple
from typing import List, Union, Dict

import textwrap

from airlatex.lib.task import AsyncDecorator

class Menu():

  def __init__(self, title=None, size=80, actions=None):
    if not title:
      title = ""
    self.title = title
    self.size = size
    if actions is None:
      actions = {}
    self.Item = _make_menu_item(actions)
    self._handlers = {}
    self.entries = []
    self.entries_by_key = {}

  def clear(self, title, size):
    self.title = title
    self.size = size
    return self

  def __call__(self, action, key):
    fn = self._handlers.get((action.__class_, key))
    if fn:
      return fn(*action)
    return None

  def add_entry(self, line, action=None, key=None, indent=0):
    if key:
      self.entries_by_key[key] = len(self.entries)
    self.entries.append(((" " * indent) + line, action))

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
        with open('menu.txt', 'a') as f:
          print(f"lookup {format} {lookup}", file=f)
        line = format.format(lookup)
      lines.append((line, item, key))
    return self.add_bulk(*lines)

  def space(self, n):
    for _ in range(n):
      self.add_entry('')

  @AsyncDecorator
  def updateEntryByKey(self, key, line):
    self.entries[self.entries_by_key[key]] = line

  def add_block(self, content, header=None):
    if header:
      if len(header) != 2:
        raise Exception("Yeah, no. You can implement this in a PR if you want")
      user, time = header

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
