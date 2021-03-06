#!/usr/bin/env python3
# -*- coding: UTF-8 -*-


import cv2
import math
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits import mplot3d


def img_scale(img, scale):
    """
    scale the input image by a same scale factor in both x and y directions
    """
    return cv2.resize(img, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)


def img_padding(img, box_size, offset, pad_num=0):
    """
    pad the image in left and right sides averagely to fill the box size

    padNum: the number to be filled (0-->(0, 0, 0)==black; 128-->(128, 128, 128)==grey)
    """
    h, w = img.shape[:2]
    assert h == box_size, 'height of the image not equal to box size'
    assert w < box_size, 'width of the image not smaller than box size'

    img_padded = np.ones((box_size, box_size, 3), dtype=np.uint8) * pad_num
    img_padded[:, box_size//2 - math.ceil(img.shape[1]/2): box_size//2 + math.ceil(img.shape[1]/2)-offset, :] = img

    return img_padded


def img_scale_squareify(img, box_size):
    """
    scale and squareify the image to get a square image with standard box size

    img: BGR image
    boxsize: the length of the square area
    """
    h, w = img.shape[:2]
    scale = box_size / h
    img_scaled = img_scale(img, scale)
    if img_scaled.shape[1] < box_size:  # h > w
        offset = img_scaled.shape[1] % 2
        img_cropped = img_padding(img_scaled, box_size, offset)
    else:  # h <= w
        img_cropped = img_scaled[:, img_scaled.shape[1]//2 - box_size//2: img_scaled.shape[1]//2 + box_size//2, :]

    assert img_cropped.shape == (box_size, box_size, 3), 'cropped image shape invalid'
    return img_cropped


def img_scale_padding(img, scale, pad_num=0):
    """
    scale and pad the image

    scale: no bigger than 1.0
    """
    assert img.shape[0] == img.shape[1]
    box_size = img.shape[0]
    img_scaled = img_scale(img, scale)
    pad_h = (box_size - img_scaled.shape[0]) // 2
    pad_w = (box_size - img_scaled.shape[1]) // 2
    pad_h_offset = (box_size - img_scaled.shape[0]) % 2
    pad_w_offset = (box_size - img_scaled.shape[1]) % 2
    img_scaled_padded = np.pad(img_scaled, ((pad_w, pad_w + pad_w_offset), (pad_h, pad_h + pad_h_offset), (0, 0)),
                               mode='constant', constant_values=pad_num)

    return img_scaled_padded


def extract_2d_joints_from_heatmap(heatmap, box_size, hm_factor):
    """
    rescale the heatmap to CNN input size, then record the coordinates of each joints

    joints_2d: a joints_num x 2 array, each row contains [row, column] coordinates of the corresponding joint
    """
    assert heatmap.shape[0] == heatmap.shape[1]
    heatmap_scaled = img_scale(heatmap, hm_factor)

    joints_2d = np.zeros((heatmap_scaled.shape[2], 2), dtype=np.int16)
    for joint_num in range(heatmap_scaled.shape[2]):
        joint_coord = np.unravel_index(np.argmax(heatmap_scaled[:, :, joint_num]), (box_size, box_size))
        joints_2d[joint_num, :] = joint_coord

    return joints_2d


def extract_3d_joints_from_heatmap(joints_2d, x_hm, y_hm, z_hm, box_size, hm_factor):
    """
    obtain the 3D coordinates of each joint from its 2D coordinates

    joints_3d: a joints_num x 3 array, each row contains [x, y, z] coordinates of the corresponding joint

    Notation:
    x direction: left --> right
    y direction: up --> down
    z direction: forawrd --> backward
    """
    scaler = 100
    joints_3d = np.zeros((x_hm.shape[2], 3), dtype=np.float32)

    for joint_num in range(x_hm.shape[2]):
        coord_2d_h, coord_2d_w = joints_2d[joint_num][:]

        joint_x = x_hm[max(int(coord_2d_h/hm_factor), 1), max(int(coord_2d_w/hm_factor), 1), joint_num] * scaler
        joint_y = y_hm[max(int(coord_2d_h/hm_factor), 1), max(int(coord_2d_w/hm_factor), 1), joint_num] * scaler
        joint_z = z_hm[max(int(coord_2d_h/hm_factor), 1), max(int(coord_2d_w/hm_factor), 1), joint_num] * scaler
        joints_3d[joint_num, :] = [joint_x, joint_y, joint_z]

    # Subtract the root location to normalize the data
    joints_3d -= joints_3d[14, :]

    return joints_3d


def draw_limbs_2d(img, joints_2d, limb_parents):
    for limb_num in range(len(limb_parents)):
        x1 = joints_2d[limb_num, 0]
        y1 = joints_2d[limb_num, 1]
        x2 = joints_2d[limb_parents[limb_num], 0]
        y2 = joints_2d[limb_parents[limb_num], 1]
        length = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
        deg = math.degrees(math.atan2(x1 - x2, y1 - y2))
        polygon = cv2.ellipse2Poly((int((y1 + y2) / 2), int((x1 + x2) / 2)), (int(length / 2), 3), int(deg), 0, 360, 1)
        img = cv2.fillConvexPoly(img, polygon, color=(38, 73, 170))
    return img


def draw_limbs_3d(ax, joints_3d, limb_parents):
    # ax.clear()
    for i in range(joints_3d.shape[0]):
        x_pair = [joints_3d[i, 0], joints_3d[limb_parents[i], 0]]
        y_pair = [joints_3d[i, 1], joints_3d[limb_parents[i], 1]]
        z_pair = [joints_3d[i, 2], joints_3d[limb_parents[i], 2]]
        ax.plot(x_pair, y_pair, zs=z_pair, linewidth=3)


def gen_heatmap(img_shape, center, sigma=3):
    img_height, img_width = img_shape
    heatmap = np.zeros((img_height, img_width), dtype=np.float32)
    center_x, center_y = center
    th = 4.6052
    delta = math.sqrt(th * 2)
    x0 = int(max(0, center_x - delta * sigma))
    y0 = int(max(0, center_y - delta * sigma))
    x1 = int(min(img_width, center_x + delta * sigma))
    y1 = int(min(img_height, center_y + delta * sigma))
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = (x - center_x) ** 2 + (y - center_y) ** 2
            exp = d / 2.0 / sigma / sigma
            if exp > th:
                continue
            heatmap[y][x] = np.clip(heatmap[y][x], math.exp(-exp), 1.0)
    return heatmap
