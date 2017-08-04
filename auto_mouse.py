from pymouse import PyMouse
from time import sleep
"""Grab the current mouse cursor position and then start the loop
If the current position of the cursor is in the same location it was last recorded in then the system is idle.  Click the left mouse button and sleep for 2 minutes
If its not equal to the last position then the mouse is not idle.  Grab the new location and sleep for 2 minutes
"""
m = PyMouse()
cursor_position = m.position()
while True:
    if cursor_position == m.position():
        m.click(cursor_position[0], cursor_position[1], button=1)
        sleep(120)
    else:
        cursor_position = m.position()
        sleep(120)
