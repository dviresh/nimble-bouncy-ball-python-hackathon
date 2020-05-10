import argparse
import asyncio
import logging
import time
import pygame
from PIL import Image
import cv2 
import numpy as np

from multiprocessing import Process, Value, Lock
import threading

from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling

def channel_log(channel, t, message):
    #print("recoeved from server")
    #print("channel(%s) %s %s" % (channel.label, t, message))
    print("ok")
def channel_send(channel, message):
    channel_log(channel, ">", message)
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

time_start = None

async def run_answer(pc, signaling):
    await signaling.connect()
    pygame.init()
    #pygame.display.set_caption('loaded image')
    
    screen = pygame.display.set_mode((700, 500))


    @pc.on("datachannel")
    def on_datachannel(channel):
        channel_log(channel, "-", "created by remote party")

        @channel.on("message")
        def on_message(message):
            # channel_log(channel, "<", message)

            # image message data in bytes to PIL image
            pil_image = Image.frombytes('RGB', (700, 500), message)
            
            # converting PIL image to pygame image - to display on surface 
            pygame_img = pygame.image.fromstring(pil_image.tobytes(), (700,500), 'RGB')
            
            # copying the image surface object 
            # to the display surface object at 
            # (0, 0) coordinate.  
            screen.blit(pygame_img, (0,0))
            # displaying the image on a pygame screen 
            #pygame.display.update()
            
            # converting pygame surface to a 3d array
            pygame_surface_array = pygame.surfarray.array3d(pygame.display.get_surface())
            
            # Transpose image - swap width with height.
            #  PyGame uses (X,Y) but CV2 use (Y,X) like matrixLoc
            cv_image = cv2.transpose(pygame_surface_array)

            # convert from RGB (used in PyGame) to BGR (used in CV2)
            cv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2BGR)
            ball_x_coordinate = Value('i', 0)
            ball_y_coordinate = Value('i', 0)
            image_processing_thread = Process(target = image_processing, 
                                                args=(cv_image,ball_x_coordinate, ball_y_coordinate) )
            image_processing_thread.start()
            image_processing_thread.join()
        
            print("x coordinate value")
            print(ball_x_coordinate.value)
            print("y coordintae value")
            print(ball_y_coordinate.value)
            
            channel_send(channel, str(ball_x_coordinate.value)+","+str(ball_y_coordinate.value))   

    await consume_signaling(pc, signaling)

def image_processing(image_to_be_processed, ball_x_coordinate, ball_y_coordinate):
    
    height, width, depth = image_to_be_processed.shape
    print (height, width, depth)
    thresh = 132
    imgray = cv2.cvtColor(image_to_be_processed,cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(imgray,(5,5),0)
    edges = cv2.Canny(blur,thresh,thresh*2)
    contours, hierarchy = cv2.findContours(edges,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    cnt = contours[0]
    cv2.drawContours(image_to_be_processed,contours,-1,(0,255,0),-1)

    # centroid_x = M10/M00 and centroid_y = M01/M00
    M = cv2.moments(cnt)
    x = int(M['m10']/M['m00'])
    y = int(M['m01']/M['m00'])
    
    ball_x_coordinate.value = x
    ball_y_coordinate.value = y
    print("printing x and y")
    print(x,y) 
    # print(width/2.0,height/2.0) 
    # print(width/2-x,height/2-y) 

    cv2.circle(image_to_be_processed,(x,y),1,(0,0,255),2)
    cv2.putText(image_to_be_processed,"center of Circle contour", (x,y), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255))
    cv2.circle(image_to_be_processed,(int(width/2),int(height/2)),1,(255,0,0),2)
    # cv2.putText(image_to_be_processed,"center of image", (int(width/2),int(height/2)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0))
    cv2.imshow('contour',image_to_be_processed)
    cv2.waitKey(500)

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
    if args.role == "answer":
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