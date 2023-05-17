import math


class FenwickTree:
    def __init__(self, size=512):
        self.size = size
        self.tree = [0] * (size + 1)
        self.array = [0] * size
        self.last_index = -1

    def initialize(self, a):
      self.size = max(size, 2**int(math.log2(len(a)) + 1))
      self.last_index = len(a) - 1
      # TODO fix remove and insert
      for i in range(len(a)):
          self.tree[i] += a[i]
          r = i | (i + 1)
          if r < self.last_index:
              self.tree[r] += self.tree[i]

    def update(self, index, diff):
        while index <= self.last_index:
            self.tree[index] += diff
            index += index & -index

    def get_cumulative_value(self, index):
        sum = 0
        while index > 0:
            sum += self.tree[index]
            index -= index & -index
        return sum

    def append(self, value):
        index = self.last_index + 1
        if index >= self.size:
            self.resize(index * 2)
        diff = value - self.array[index]
        self.array[index] = value
        self.update(index + 1, diff)
        self.last_index = index

    def remove(self, index):
        if index < 0:
            # We don't offset by 1 here, because we want the range to capture
            # include self.last_index
            if index == -1:
              self.update(index, -self.array[-1])
            index = self.last_index + index + 1

        for i in range(index, self.last_index):
          diff = self.array[i + 1] - self.array[i]
          r = i + (i & -i)
          if r < self.size:
            self.tree[r] += diff
          self.tree[i] += diff
          self.array[i] = self.array[i + 1]
        self.array[self.last_index] = 0
        self.last_index -= 1

    def insert(self, index, value):
        if index + 1 >= self.size:
            self.array.insert(index, value)
            return self.resize(index * 2)

        if index < 0:
            index = self.last_index + index + 1
        if index >= self.last_index:
            return self.append(value)

        previous = self.array[index]
        for i in range(index, self.last_index + 1):
          diff = previous - self.array[i]
          r = i + (i & -i)
          if r < self.size:
            self.tree[r] += diff
          self.tree[i] += diff
          self.array[i], previous = previous, self.array[i]
        self.last_index += 1


    def resize(self, new_size):
        new_tree = FenwickTree(new_size)
        new_tree.initialize(self.array)
        self.size = new_size
        self.tree = new_tree.tree
        self.array = new_tree.array

    def position(self, row, col):
      return self[row] + col

    def search(self, v):
        if v > self.get_cumulative_value(self.last_index + 1):
            return -1, None
        k = 0
        bit_mask = 1 << (self.size.bit_length() - 1)
        while bit_mask != 0 and k < self.size:
            mid = k + bit_mask
            if mid <= self.size and v > self.tree[mid]:
                k = mid
                v -= self.tree[mid]
            bit_mask >>= 1
        return k, v

    def __getitem__(self, index):
        if index == -1:
            index = self.last_index + 1
        return self.get_cumulative_value(index + 1)

    def __setitem__(self, index, value):
        if index == -1:
            index = self.last_index + 1
        self.insert(index, value)

    def __delitem__(self, index):
        if index == -1:
            index = self.last_index + 1
        self.remove(index)

class NaiveAccumulator:
    def __init__(self, size=512):
        self.size = size
        self.array = [0] * size

    def insert(self, index, value):
        self.array.insert(index - 1, value)

    def get_cumulative_value(self, index):
        return sum(self.array[:index])

    def remove(self, index):
        del self.array[index]

    def resize(self, new_size):
        if new_size > self.size:
            self.array += [0] * (new_size - self.size)
        else:
            self.array = self.array[:new_size]
        self.size = new_size

    def search(self, v):
      t = 0
      for i, c in enumerate(self.array):
        if t + c >= v:
          return i, v - t
        t += c
      return -1, None

    def position(self, row, col):
      return self[row] + col

    def __getitem__(self, index):
        return self.get_cumulative_value(index + 1)

    def __setitem__(self, index, value):
        if index >= self.size:
            self.resize(index * 2)
        self.array[index] = value

    def __delitem__(self, index):
        self.remove(index)
