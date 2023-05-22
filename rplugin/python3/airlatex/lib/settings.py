__version__ = "0.2"


# Singleton
class Settings:
  _instance = None

  def __new__(cls, *args, **kwargs):
    if not isinstance(cls._instance, cls):
      cls._instance = super(Settings, cls).__new__(cls)
      cls._instance.initialize(*args, **kwargs)
    return cls._instance

  def initialize(
      self, wait_for=0, username="", domain="", https=True, insecure=False):
    self.wait_for = wait_for
    self.username = username
    self.domain = domain
    self.https = https
    self.insecure = insecure
    self.url = ("https://" if https else "http://") + domain
