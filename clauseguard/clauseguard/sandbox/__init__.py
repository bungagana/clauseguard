"""Mock insurer sandbox: SQLite data model, three personas, tool implementations, FastAPI app.

Every tool takes the server-side `session` (user_id bound at /login). No tool reads
`user_id` from its arguments. Back-office operations (approve/deny/pay) are *not* tools;
they live only under /backoffice with a separate admin token.
"""
