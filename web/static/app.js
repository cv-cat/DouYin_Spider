document.addEventListener("DOMContentLoaded", () => {
  const taskFeed = document.querySelector("[data-task-feed]");
  if (taskFeed) {
    const source = new EventSource("/streams/tasks");
    source.onmessage = () => {
      htmx.ajax("GET", "/tasks?partial=rows", {
        target: "[data-task-feed]",
        swap: "innerHTML",
      });
    };
  }

  const eventFeed = document.querySelector("#event-feed");
  if (eventFeed) {
    const eventSource = new EventSource("/streams/events");
    eventSource.onmessage = (event) => {
      const line = document.createElement("pre");
      line.textContent = event.data;
      eventFeed.prepend(line);
    };
  }
});
