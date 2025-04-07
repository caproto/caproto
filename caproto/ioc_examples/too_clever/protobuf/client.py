from caproto.sync.client import read as _read, write as _write, subscribe

from structured_image import encode, decode


def write(pv, frame, image):
    payload = encode(frame, image)
    _write(pv, payload)


def read(pv):
    payload = _read(pv)
    frame, image = decode(payload.data.tobytes())
    return frame, image


def monitor(pv):
    def print_image(sub, response):
        frame, image = decode(response.data.tobytes())
        print(f"{frame=}: {image=}")

    sub = subscribe(pv)
    sub.add_callback(print_image)
    sub.block()


if __name__ == "__main__":
    import sys

    monitor(sys.argv[1])
