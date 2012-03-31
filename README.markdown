opinionated deployment. TODO - write some docs here.

But you probably want a fabfile that looks like this:

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "deployinator"))
    from deployinator import *

    fab_init("feedify",
        database = "feedify",
        rules = {
            "nginx": "deploy/nginx.conf",
            "gunicorn": {
                "port": 8002,
            }
        }
    )
