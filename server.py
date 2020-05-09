import argparse
import asyncio
import logging
import time
import threading 

from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling
# ----------- below section of the code is for bouncy ball creation ---------------------- 

import pygame
import random

from io import StringIO
from PIL import Image

# Define some colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
 
SCREEN_WIDTH = 700
SCREEN_HEIGHT = 500
BALL_SIZE = 25

# create ball bouncing across the screen
pygame.init()

# Set the height and width of the screen
size = [SCREEN_WIDTH, SCREEN_HEIGHT]
screen = pygame.display.set_mode(size)

image_data = "empty"
image_data_lock = threading.Lock()
class Ball:
    """
    Class to keep track of a ball's location and vector.
    """
    def __init__(self):
        self.x = 0
        self.y = 0
        self.change_x = 0
        self.change_y = 0
 
 
def make_ball():
    """
    Function to make a new, random ball.
    """
    ball = Ball()
    # Starting position of the ball.
    # Take into account the ball size so we don't spawn on the edge.
    ball.x = random.randrange(BALL_SIZE, SCREEN_WIDTH - BALL_SIZE)
    ball.y = random.randrange(BALL_SIZE, SCREEN_HEIGHT - BALL_SIZE)
 
    # Speed and direction of rectangle
    ball.change_x = random.randrange(-2, 3)
    ball.change_y = random.randrange(-2, 3)
 
    return ball



# ---------------------- below section of the code if for server communication -------

def channel_log(channel, t, message):
    #print("channel(%s) %s %s" % (channel.label, t, message))
    print("recieved from client")

def channel_send(channel, message):
    channel_log(channel, ">", message)
    channel.send(message)

{"sdp": "v=0\r\no=- 3798035874 3798035874 IN IP4 0.0.0.0\r\ns=-\r\nt=0 0\r\na=group:BUNDLE 0\r\na=msid-semantic:WMS *\r\nm=application 51529 DTLS/SCTP 5000\r\nc=IN IP4 192.168.1.13\r\na=mid:0\r\na=sctpmap:5000 webrtc-datachannel 65535\r\na=max-message-size:65536\r\na=candidate:d27094500494667636f3d2a47dc259db 1 udp 2130706431 192.168.1.13 51529 typ host\r\na=candidate:ab44e0e64d150378a4d5ed3100dc7394 1 udp 1694498815 174.55.165.41 51529 typ srflx raddr 192.168.1.13 rport 51529\r\na=end-of-candidates\r\na=ice-ufrag:p2n4\r\na=ice-pwd:doJsGyaVBlzwh4xd7ep8h7\r\na=fingerprint:sha-256 B5:43:0C:E4:5A:1E:F9:BD:0B:1E:C3:26:54:BD:B5:0E:90:3A:03:08:20:B2:DB:DC:ED:AE:30:C8:D8:49:F7:DE\r\na=setup:active\r\n", "type": "answer"}
async def consume_signaling(pc, signaling):
    while True:
        obj = await signaling.receive()

        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)

            if obj.type == "offer":
                # send answer
                await pc.setLocalDescription(await pc.createAnswer())
                await signaling.send(pc.localDescription)
        elif isinstance(obj, RTCIceCandidate):
            await pc.addIceCandidate(obj)
        elif obj is BYE:
            print("Exiting")
            break

def current_stamp():
    global time_start

    if time_start is None:
        time_start = time.time()
        return 0
    else:
        return int((time.time() - time_start) * 1000000)

time_start = None


def generate_bouncing_ball():
    # Used to manage how fast the screen updates
    clock = pygame.time.Clock()
 
    ball_list = []
 
    ball = make_ball()
    ball_list.append(ball)

    while True:
        for ball in ball_list:
            # Move the ball's center
            ball.x += ball.change_x
            ball.y += ball.change_y
 
            # Bounce the ball if needed
            if ball.y > SCREEN_HEIGHT - BALL_SIZE or ball.y < BALL_SIZE:
                ball.change_y *= -1
            if ball.x > SCREEN_WIDTH - BALL_SIZE or ball.x < BALL_SIZE:
                ball.change_x *= -1
        
        # --- Drawing
        # Set the screen background
        screen.fill(BLACK)
        # Draw the balls
        for ball in ball_list:
            pygame.draw.circle(screen, WHITE, [ball.x, ball.y], BALL_SIZE)

        # --- Wrap-up
        # Limit to 60 frames per second
        clock.tick(60)
 
        # Go ahead and update the screen with what we've drawn.
        pygame.display.flip()
        # ball_image_surface = pygame.display.get_surface()
        image_data_lock.acquire()
        global image_data 
        image_data = pygame.image.tostring(screen, 'RGBA') 
        # img = Image.frombytes('RGBA',(), image_data)
        # zdata = StringIO()
        # img.save(zdata, "JPEG")
        # image_data = zdata.getvalue()
        image_data_lock.release()

        # fname = "ball_images/ball.png"
        # pygame.image.save(screen, fname)

async def run_offer(pc, signaling):
    await signaling.connect()

    channel = pc.createDataChannel("chat") # ------------- instead of creating datachanel, send video 
    channel_log(channel, "-", "created by local party")
    
    # generating a bouncing ball
    gererate_ball_thread = threading.Thread(target= generate_bouncing_ball)
    gererate_ball_thread.start()
    
    async def send_pings():
        while True:
            #channel_send(channel, "ping %d" % current_stamp())
            image_data_lock.acquire()
            global image_data
            channel_send(channel, image_data)
            image_data_lock.release()
            await asyncio.sleep(1)

    @channel.on("open")
    def on_open():
        asyncio.ensure_future(send_pings())

    @channel.on("message")
    def on_message(message):
        channel_log(channel, "<", message)

        # if isinstance(message, str) and message.startswith("pong"):
        #     elapsed_ms = (current_stamp() - int(message[5:])) / 1000
        #     print(" RTT %.2f ms" % elapsed_ms)

    # send offer
    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)

    await consume_signaling(pc, signaling)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data channels ping/pong")
    parser.add_argument("role", choices=["offer", "answer"])
    parser.add_argument("--verbose", "-v", action="count")
    add_signaling_arguments(parser)

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    signaling = create_signaling(args)
    pc = RTCPeerConnection()
    if args.role == "offer":
        coro = run_offer(pc, signaling)
    else:
        coro = run_answer(pc, signaling)

    # run event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(coro)
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(pc.close())
        loop.run_until_complete(signaling.close())