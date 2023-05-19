import requests
from bs4 import BeautifulSoup


class WebPage:

  def __init__(self, client, url, allow_redirects=True):
    self.client = client
    self.allow_redirects = allow_redirects
    self.url = url
    self.page = None
    self.soup = None
    self.load()

  def load(self):
    try:
      self.page = self.client.get(
          self.url, allow_redirects=self.allow_redirects)
      self.page.raise_for_status()
      self.soup = BeautifulSoup(self.page.content, 'html.parser')
    except requests.exceptions.HTTPError as err:
      raise Exception(f"HTTP error occurred: {err}")
    except Exception as err:
      raise Exception(f"Other error occurred: {err}")

  def parse(self, name, tag='meta'):
    if self.soup is not None:
      element = self.soup.find(tag, {'name': f"ol-{name}"})
      if element:
        return Tag(element)
      else:
        raise Exception(
            f"Couldn't find an element with name {name} on the page.")
    else:
      raise Exception("The page hasn't been loaded correctly.")

  @property
  def ok(self):
    return self.page.ok if self.page else False

  @property
  def text(self):
    return self.page.text.encode() if self.page else ""


class Tag:

  def __init__(self, bs4_tag):
    self.tag = bs4_tag

  @property
  def content(self):
    return self.tag.get('content', None) if self.tag else None
