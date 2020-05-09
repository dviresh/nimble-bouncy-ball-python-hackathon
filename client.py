import argparse
import asyncio
import logging
import time
import pygame
from PIL import Image
import cv2 as cv
import numpy as np
import base64

from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling

def channel_log(channel, t, message):
    print("recoeved from server")

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
    pygame.display.set_caption('loaded image')
    
    screen = pygame.display.set_mode((700, 500))


    @pc.on("datachannel")
    def on_datachannel(channel):
        channel_log(channel, "-", "created by remote party")

        @channel.on("message")
        def on_message(message):
            channel_log(channel, "<", message)

            # image message data in bytes to PIL image
            pil_image = Image.frombytes('RGB', (700, 500), message)
            
            # converting PIL image to pygame image - to display on surface 
            pygame_img = pygame.image.fromstring(pil_image.tobytes(), (700,500), 'RGB')
            
            # copying the image surface object 
            # to the display surface object at 
            # (0, 0) coordinate.  
            screen.blit(pygame_img, (0,0))
            # displaying the image on a pygame screen 
            pygame.display.update()
            
            # converting pygame surface to a 3d array
            pygame_surface_array = pygame.surfarray.array3d(pygame.display.get_surface())
            
            # Transpose image - swap width with height.
            #  PyGame uses (X,Y) but CV2 use (Y,X) like matrix 
            # in math (other words (row, column))
            cv_image = cv.transpose(pygame_surface_array)
            
            # onvert from RGB (used in PyGame) to BGR (used in CV2)
            cv_image = cv.cvtColor(cv_image, cv.COLOR_RGB2BGR)
            
            # displaying the image
            cv.imshow('Color', cv_image)
            cv.waitKey(0)
            cv.destroyAllWindows()
            
            channel_send(channel, "pong")

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