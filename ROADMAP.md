# Roadmap

Here are the outstanding tasks for `py-st`.

- Investigate openapi-python-client or rolling my own method to turn SpaceTraders.json spec automatically into client prototypes.
- Implement a simple file-based cache for ships and waypoints to speed up gameplay and reduce manual data entry.
  - Connect the game data cache into commands so I don't have to type ship and system names each time (e.g., allow --ship 1 or --wp 3).
  - Might have a dirty flag and last-updated-time so I can know what needs to be re-fetched

- Improve web requests.
  - We have _make_request, which handles 409s.
  - This could be expanded to handle 400s when we request something impossible (e.g. not enough fuel)
  - Rate limiting and backoff logic needs to be much improved.
    - Rate limits are per account, not per command.
    - 2 requests/second max, burst up to 30 requests per 60 seconds.
    - Returns 429
    - Whole page of response error codes at https://spacetraders.io/api-guide/response-errors
    - I really just want to see the whole response when it fails
  - While waiting for something to cool down, can do other work. Might eventually implement a queue and threading

- Connect game data cache into commands so I don't have to type ship and system names each time
- Develop a script to run a basic ship automation loop.

- I'm unhappy with the hardcoded test factories. Can we find a way to create objects from the models to use in testing? Perhaps more info comes from the json. Maybe we just need to fetch and keep the json instead of discarding it after we create the model classes (done in the Makefile)
- I'm unhappy with the unit testing level of detail. Don't think it will actually catch problems in refactoring.

- Update to latest version of Python

## GUI
- Research and select a GUI framework (e.g., PySide6, Tkinter).
- Design a basic UI to display universe/fleet data and trigger actions.
- Implement the GUI, ensuring it runs in a separate thread from the automation logic.
