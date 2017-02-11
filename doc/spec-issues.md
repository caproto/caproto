# Variations from the EPICS Channel Access Spec

* SearchResponse payload_size is fixed at 2, not 8 as documented.
* EventCancelResponse seems to come back managed with the wrong command field
  and the wrong data_count field.
* ReadNotifyResponse and WriteNotifyResponse have a status_code, not an sid. The
  client-provided ioid must be used to associated responses with requests (and
  associated channels).

Additionally, various formatting irregularities have been fixed in our vendored
copy of CAproto.html.
