import collections.abc
from weakref import proxy


class Link:
    """
    Represents a node in a doubly linked list. It contains references to the
    previous and next nodes, the stored key, and a weak reference to itself.
    """

    __slots__ = 'prev', 'next', 'key', '__weakref__'


class OrderedSet(collections.abc.MutableSet):
    """
    Set that remembers the order elements were added. Provides O(1) time complexity
    for add, remove, and check operations, similar to regular sets.
    """

    # Big-O running times for all methods are the same as for regular sets.
    # The internal self.__map dictionary maps keys to links in a doubly linked list.
    # The circular doubly linked list starts and ends with a sentinel element.
    # The sentinel element never gets deleted (this simplifies the algorithm).
    # The prev/next links are weakref proxies (to prevent circular references).
    # Individual links are kept alive by the hard reference in self.__map.
    # Those hard references disappear when a key is deleted from an OrderedSet.

    def __init__(self, iterable=None):
        """
        Initializes an empty OrderedSet. If an iterable is provided, adds its elements
        to the set.
        """
        self.__root = root = Link()  # sentinel node for doubly linked list
        root.prev = root.next = root
        self.__map = {}  # key --> link
        if iterable is not None:
            self |= iterable

    def __len__(self):
        """
        Returns the number of elements in the OrderedSet.
        """
        return len(self.__map)

    def __contains__(self, key):
        """
        Checks if a key is in the OrderedSet.
        """
        return key in self.__map

    def add(self, key):
        """
        Adds a key to the OrderedSet, storing it in a new link at the end of the linked
        list.
        """
        if key not in self.__map:
            self.__map[key] = link = Link()
            root = self.__root
            last = root.prev
            link.prev, link.next, link.key = last, root, key
            last.next = root.prev = proxy(link)

    def discard(self, key):
        # Remove an existing item using self.__map to find the link which is
        """
        Removes an existing item using self.__map to find the link, which is then
        removed by updating the links in the predecessor and successor.
        """
        if key in self.__map:
            link = self.__map.pop(key)
            link.prev.next = link.next
            link.next.prev = link.prev

    def __iter__(self):
        """
        Traverses the linked list in order, yielding each key.
        """
        root = self.__root
        curr = root.next
        while curr is not root:
            yield curr.key
            curr = curr.next

    def __reversed__(self):
        """
        Traverses the linked list in reverse order, yielding each key.
        """
        root = self.__root
        curr = root.prev
        while curr is not root:
            yield curr.key
            curr = curr.prev

    def pop(self, last=True):
        """
        Removes and returns the last item if 'last' is True, otherwise removes and
        returns the first item. Raises KeyError if the set is empty.
        """
        if not self:
            raise KeyError('set is empty')
        key = next(reversed(self)) if last else next(iter(self))
        self.discard(key)
        return key

    def __repr__(self):
        """
        Returns a string representation of the OrderedSet.
        """
        if not self:
            return f'{self.__class__.__name__}()'
        return f'{self.__class__.__name__}({list(self)!r})'

    def __eq__(self, other):
        """
        Checks if two OrderedSets are equal by comparing their lengths and elements, or
        checks if they are disjoint if the other object is not an OrderedSet.
        """
        if isinstance(other, OrderedSet):
            return len(self) == len(other) and list(self) == list(other)
        return not self.isdisjoint(other)
