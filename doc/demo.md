Just showing off that bytes can be read directly into a ctypes Structure:
```python
In [567]: d1 = DBR_CTRL_INT(status=1,precision=3,units='asdf'.encode(),upper_alarm_limit=50)

In [568]: b = bytes(d1)

In [569]: b
Out[569]:
b'\x00\x01\x00\x00\x00\x03asdf\x00\x00\x00\x00\x00\x00\x00\x00\x002\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

In [570]: d2 = DBR_CTRL_INT()

In [571]: BytesIO(b).readinto(d2)
Out[571]: 32

In [573]: d1.units
Out[573]: b'asdf'

In [574]: d2.units
Out[574]: b'asdf'

In [575]: d1.upper_alarm_limit == d2.upper_alarm_limit
Out[575]: True
```
