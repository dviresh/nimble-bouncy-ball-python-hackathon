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
from subprocess import *
import cv2
import math
from scipy.spatial import distance

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

ball_x_coordinate_client = 0
ball_y_coordinate_client = 0
ball_coordinate_lock = threading.Lock()
error_between_coordinates = None
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

# def channel_log(channel, t, message):
#     print("channel(%s) %s %s" % (channel.label, t, message))
    #print("channel(%s) %s %s" % (channel.label, t, message))
    #print("ok")
def channel_send(channel, message):
    #channel_log(channel, ">", message)
    channel.send(message)

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

        # --- Wrap-upball
        # Limit to 60 frames per second
        clock.tick(60)
 
        # Go ahead and update the screen with what we've drawn.
        pygame.display.flip()
        # ball_image_surface = pygame.display.get_surface()
        image_data_lock.acquire()
        global image_data 
        image_data = pygame.image.tostring(screen, 'RGB') 
        
        image_data_lock.release()

        # below section of the code will get coordinates of ball
        # running on the server

        # converting pygame surface to a 3d array
        pygame_surface_array = pygame.surfarray.array3d(pygame.display.get_surface())

        # Transpose image - swap width with height.
        #  PyGame uses (X,Y) but CV2 use (Y,X) like matrixLoc
        cv_image = cv2.transpose(pygame_surface_array)

        # convert from RGB (used in PyGame) to BGR (used in CV2)
        cv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2BGR)

        # processing the cv image to get the ball coordinates
        
        height, width, depth = cv_image.shape
        # print (height, width, depth)
        thresh = 132
        imgray = cv2.cvtColor(cv_image,cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(imgray,(5,5),0)
        edges = cv2.Canny(blur,thresh,thresh*2)
        contours, hierarchy = cv2.findContours(edges,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
        cnt = contours[0]
        cv2.drawContours(cv_image,contours,-1,(0,255,0),-1)

        # centroid_x = M10/M00 and centroid_y = M01/M00
        M = cv2.moments(cnt)
        ball_x_coordinate_server = int(M['m10']/M['m00'])
        ball_y_coordinate_server = int(M['m01']/M['m00'])
        
        global ball_coordinate_lock
        global ball_x_coordinate_client
        global ball_y_coordinate_client
        global error_between_coordinates
        ball_coordinate_lock.acquire()
        # computing the error between the ball coordinates of server and client
        # using euclidean distance

        ball_coordinates_server = (ball_x_coordinate_server,ball_y_coordinate_server)
        ball_coordinates_client = (ball_x_coordinate_client, ball_y_coordinate_client)
        
        error_between_coordinates = distance.euclidean(ball_coordinates_server, ball_coordinates_client)
        
        ball_coordinate_lock.release() 

        cv2.circle(cv_image,(ball_x_coordinate_server,ball_y_coordinate_server),1,(0,0,255),2)
        cv2.putText(cv_image,"center of Circle contour", (ball_x_coordinate_server,ball_y_coordinate_server), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255))
        cv2.circle(cv_image,(int(width/2),int(height/2)),1,(255,0,0),2)
        cv2.imshow('contour image on server',cv_image)
        cv2.waitKey(500)


async def run_offer(pc, signaling):
    await signaling.connect()

    channel = pc.createDataChannel("chat") 
    #channel_log(channel, "-", "created by local party")
    
    # generating a bouncing ball
    gererate_ball_thread = threading.Thread(target= generate_bouncing_ball)
    gererate_ball_thread.start()
    
    async def send_pings():
        while True:
            #channel_send(channel, "ping %d" % current_stamp())
            image_data_lock.acquire()
            global image_data# print(rec_message.split(","))
        
            channel_send(channel, image_data)
            image_data_lock.release()
            await asyncio.sleep(1)

    @channel.on("open")
    def on_open():
        asyncio.ensure_future(send_pings())

    @channel.on("message")
    def on_message(rec_message):
        #channel_log(channel, "<", rec_message)
        # print("channel(%s) %s" % (channel.label, rec_message))
        ball_coordinates_client = rec_message.split(",") 
        
        global ball_coordinate_lock
        global ball_x_coordinate_client
        global ball_y_coordinate_client
        global error_between_coordinates

        ball_coordinate_lock.acquire()
        ball_x_coordinate_client = int(ball_coordinates_client[0])
        ball_y_coordinate_client = int(ball_coordinates_client[1])

        print("error between the coordinates")
        print(error_between_coordinates)
        ball_coordinate_lock.release()

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