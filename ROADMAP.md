# Roadmap

Here are the outstanding tasks for `py-st`.

- Progress the file-based cache for ships and waypoints to speed up gameplay and reduce manual data entry.
  - Connect the game data cache into commands so I don't have to type ship and system names each time (e.g., allow --ship 1 or --wp 3).
- Refactor services.py to split services into sensible parts.
  - Unit test of services.py before or after the refactor?

- Develop a script to run a basic ship automation loop.

- Investigate openapi-python-client or rolling my own method to turn SpaceTraders.json spec automatically into client prototypes.
- Currently using agent tokens, which expire every week. Explore Register by API (https://spacetraders.io/quickstart/new-game) with an account token, then automatically create a new agent if none exist.

- Improve web requests.
  - We have transport.py request_json, which handles 409s and 429s.
  - Rate limiting and backoff logic has room for improvement but is okay for now
    - Rate limits are per account, not per command.
    - 2 requests/second max, burst up to 30 requests per 60 seconds.
    - Whole page of response error codes at https://spacetraders.io/api-guide/response-errors
    - Do I see the whole response when it fails?
  - While waiting for something to cool down (e.g. ship travel), can do other work. Might eventually implement a queue and threading

- I'm unhappy with the unit testing level of detail. Don't think it will actually catch problems in refactoring.

## GUI
- Research and select a GUI framework (e.g., PySide6, Tkinter).
- Design a basic UI to display universe/fleet data and trigger actions.
- Implement the GUI, ensuring it runs in a separate thread from the automation logic.
