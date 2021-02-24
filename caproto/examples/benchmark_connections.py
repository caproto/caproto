"""
Analyze IOCs response times for channel creation (connection).

Example:

$ python benchmark.py some_network_traffic.pcap
0 channel creation requests were unanswered during this capture.


Raw data:
          PV  server_address             t        dt
0   simple:A   192.168.86.22  1.614185e+09  0.014851
1   simple:B   192.168.86.22  1.614185e+09  0.014851
2   simple:C   192.168.86.22  1.614185e+09  0.014851
3  rpi:color  192.168.86.245  1.614185e+09  0.150308


Aggregated stats by server address:
                count      mean  std       min       25%       50%       75%       max
server_address
192.168.86.22     3.0  0.014851  0.0  0.014851  0.014851  0.014851  0.014851  0.014851
192.168.86.245    1.0  0.150308  NaN  0.150308  0.150308  0.150308  0.150308  0.150308
"""
from collections import namedtuple
from caproto import CreateChanRequest, CreateChanResponse
from caproto.sync.shark import shark
import pandas
import sys


Pair = namedtuple("Pair", ["request", "response"])
Record = namedtuple("Record", ["PV", "server_address", "t", "dt"])


def match_request_and_response(parsed):
    "From a stream of parsed CA traffic, extract channel creation request/response pairs."
    unanswered_requests = {}
    pairs = []
    for item in parsed:
        command = item.command
        if isinstance(command, CreateChanRequest):
            unanswered_requests[command.cid] = item
        elif isinstance(command, CreateChanResponse):
            request_item = unanswered_requests.pop(command.cid, None)
            pairs.append(Pair(request_item, item))
    return pairs, list(unanswered_requests.values())


def build_record_from_request_and_response_pair(pair):
    "Extract PV name, server address, absolute time t, and request/response dt."
    request, response = pair
    record = Record(
        PV=request.command.name,
        server_address=request.dst,
        t=request.timestamp,
        dt=response.timestamp - request.timestamp
    )
    return record


def main(filepath):
    with open(filepath, "rb") as file:
        parsed = shark(file)
        pairs, unanswered = match_request_and_response(parsed)
    print(f"{len(unanswered)} channel creation requests were unanswered during this capture.")
    records = [build_record_from_request_and_response_pair(pair) for pair in pairs]
    if not records:
        print("Nothing to analyze.")
        sys.exit(1)
    df = pandas.DataFrame.from_records(records, columns=Record._fields)
    server_stats = df.groupby("server_address")["dt"].describe()
    print("\n\nRaw data:")
    print(df)

    print("\n\nAggregated stats by server address:")
    print(server_stats)


if __name__ == "__main__":
    main(sys.argv[1])
