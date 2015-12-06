# wakeup
Controller for Raspberry Pi-based wakeup light

This module depends on astral (https://pypi.python.org/pypi/astral/0.8.1) and RPi.GPIO (https://pypi.python.org/pypi/RPi.GPIO) and is capable of:

- Turning on and off the lights at determined times
- Simulated sunset and sunrise
- Flexible programming (day of the week, specific day, etc)

The control signal is output on a GPIO pin with PWM. If you want to implement the light you probably need a big transistor such as the TIP120 (I use it to drive 3A 12V).

Enjoy!
