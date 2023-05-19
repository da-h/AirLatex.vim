from collections import namedtuple
from typing import List, Union, Dict

import textwrap

class Menu():
  def __init__(self, title, size=80, actions=None):
    self.title = title
    self._handlers = {}
    self.entries = []
    if not actions:
      actions = {}
    self.Item = _make_menu_item(actions)

  def __call__(self, action, key):
    fn = self._handlers.get((action.__class_, key))
    if fn:
      return fn(*action)
    return None

  def add_entry(self, line, action=None):
    self.entries.append((line, action))

  def add_bulk(self, *lines):
    for line in lines:
      self.entries.append(*lines)

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
        key = key_format_item

      key = data.get(key, "")
      if isinstance(key, dict):
        line = format.format(**key)
      elif isinstance(key, tuple):
        line = format.format(*key)
      else:
        line = format.format(key)
      lines.append((line, item))
    return self.add_bulk(*lines)

  def space(self, n):
    for _ in range(n):
      self.add_entry('')

  def add_block(self, content, header=None):
    if header:
      if len(header) != 2:
        raise Exception("Yeah, no. You can implement this in a PR if you want")
      user, time = header

    space = size - len(user) - len(short_date) - 6
    user = f"  {user} │"
    self.add_entry(f"¶{user} {' ' * space}{short_date}")
    self.add_entry(
        "┌" + '─' * (len(user) - 1) + '┴' + '─' * (size - 2 - len(user)) +
        "┐")
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
      return type(name, (MenuItem,), {field: menu_classes[field] for field in fields})
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
    return build_class("MenuItem", data)
