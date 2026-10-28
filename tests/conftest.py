import google.auth
from google.auth.credentials import AnonymousCredentials

# app.store builds its Storage and BigQuery clients on import, which needs credentials. Every test replaces the
# calls that would use them, so give the clients anonymous ones: the tests then run on a machine with no gcloud login.
# A test that needs a real login gets these anonymous credentials too, and must undo this first.
google.auth.default = lambda *args, **kwargs: (AnonymousCredentials(), None)
