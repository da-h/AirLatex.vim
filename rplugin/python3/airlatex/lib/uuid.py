import time
import random

# github:overleaf/overleaf/959e6a73d8/libraries/ranges-tracker/index.cjs#L80
# General track changes (new comment in thread / other tc)
def generateId():
  pid = format(random.randint(0, 32767), 'x')
  machine = format(random.randint(0, 16777216), 'x')
  timestamp = format(int(time.time()), 'x')

  return (
      '00000000'[:8 - len(timestamp)] + timestamp +
      '000000'[:6 - len(machine)] + machine + '0000'[:4 - len(pid)] + pid)


# Specifically for creating comments
def generateCommentId(increment):
  increment = format(increment, 'x')  # convert to hex
  id = generateId() + ('000000' + increment)[-6:]  # pad with zeros
  return id


# Generate a timstamp with a length of 13 numbers
def generateTimeStamp():
  return str(int(time.time() * 1e13))[:13]
