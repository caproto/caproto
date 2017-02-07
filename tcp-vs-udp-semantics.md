# Notes on TCP vs UDP semantics

*in which a humble experimental physicist teaches himself networking basics*

## TCP

Server and client each create a TCP/IP socket.

```python
server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
```

Server binds its socket to a host and port.

```python
server_sock.bind((host, port))
```

Server listens to its socket.

```python
server_sock.listen(1)
```

Client tries to connect to server (same ``(host, port)`` as above).

```python
client_sock.connect((host, port))
```

Server accepts connection.
```python
conn, (client_host, client_port) = server_sock.accept()
```

Client sends into its socket.

```python
client_sock.sendall(b'message')
```

Server receives through its connection (not its socket).

```python
message = conn.recv(1024)  # some number of bytes
```

And server replies sends through its connection.

```python
conn.sendall(b'reply_message')
```

Client receives the reply from its socket.

```python
reply = client_socket.recv(1024)  # some number of bytes
```

## UDP

Server and client each create a UDP socket. Note that here we use ``SOCK_DGRAM``
where for TCP we gave ``SOCK_STREAM``.

```python
server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
```

Again, server binds its socket to a host and port.

```python
server_sock.bind((host, port))
```

Server does *not* listen or accept connections.

Instead of creating a connection, the client sends a one-off packet to the
server's address.

```python
client_sock.sendto(b'message', (host, port))
```

The server receives the client's address with the packet.

```python
(message, (client_host, client_port)) = server_sock.recvfrom(1024)
```

Using the same 'send' semantics as the client, the server sends a reply.

```python
server_sock.sendto(b'reply message', (client_host, client_port))
```

And using the same 'receive' semantics as the server, the client receives it.

```python

(reply, (host, port)) = client_sock.recvfrom(1024)
```
