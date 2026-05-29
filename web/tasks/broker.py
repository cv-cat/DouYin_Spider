from collections import defaultdict
from queue import Queue


class EventBroker:
    def __init__(self):
        self._subscribers = defaultdict(list)

    def subscribe(self, channel):
        queue = Queue()
        self._subscribers[channel].append(queue)
        return queue

    def unsubscribe(self, channel, queue):
        if queue in self._subscribers[channel]:
            self._subscribers[channel].remove(queue)

    def publish(self, channel, payload):
        for queue in list(self._subscribers[channel]):
            queue.put(payload)
