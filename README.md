# Newsroom Toolkit Python Client 

This is the source code of Newsroom Toolkit Python client.

[main.py](main.py) synchronizes Newsroom Toolkit instance content via Newsroom Toolkit API and stores local snapshot.

Articles are stored as files in `WWW_DIR`. Landing page is stored as `index` file.
Error page content stored as error.html in `WWW_DIR`.

Each update creates new Snapshot based on `checksum` field of the response.
Expired content is being moved into a snapshot-named directory inside `BIN_DIR`

To run the script set `NRTK_API_URL` and `NRTK_API_TOKEN` environment variables.

You can also set two optional envs:
- `LOGLEVEL` (str|int) to set needed Logging Level.
- `INFINITY` (str|int) in seconds to enable Infinity mode – the script will repeat sync with an interval of INFINITY.

Console Usage: 
```
$ main.py -l LOGLEVEL -i INFINITY
```
