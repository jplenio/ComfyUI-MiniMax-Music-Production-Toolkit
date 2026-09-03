import cv2
from numpy import ndarray

from . import util

def read(file_path:str) -> ndarray: #(height, width, channels)
    image:ndarray = cv2.imread(file_path)
    return image

def write(
    file_path:str, 
    image:ndarray #(height, width, channels)
) -> None:
    util.make_parent_dir(file_path)
    cv2.imwrite(file_path, image)