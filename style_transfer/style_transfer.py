import os

import cv2
import numpy as np
import torch
import torchvision.transforms as transforms
from django.conf import settings
from django.core.cache import cache
from torch.autograd import Variable

from CartoonGAN.network.Transformer import Transformer
from ComixGAN.model import ComixGAN
from utils import profile

# load pretrained model
comixGAN = ComixGAN()


class StyleTransfer():
    @classmethod
    @profile
    def get_stylized_frames(cls, frames, style_transfer_mode=0, gpu=settings.GPU):
        if style_transfer_mode == 0:
            return cls._comix_gan_stylize(frames=frames)
        elif style_transfer_mode == 1:
            return cls._cartoon_gan_stylize(frames, gpu=gpu, style='Hayao')
        elif style_transfer_mode == 2:
            return cls._cartoon_gan_stylize(frames, gpu=gpu, style='Hosoda')

    @staticmethod
    def _resize_images(frames, size=384):
        resized_images = []
        for img in frames:
            # resize image, keep aspect ratio
            h, w, _ = img.shape
            ratio = h / w
            if ratio > 1:
                h = size
                w = int(h * 1.0 / ratio)
            else:
                w = size
                h = int(w * ratio)
            resized_img = cv2.resize(img, (w, h))
            resized_images.append(resized_img)
        return resized_images

    @classmethod
    def _comix_gan_stylize(cls, frames):
        if max(frames[0].shape) > settings.MAX_FRAME_SIZE_FOR_STYLE_TRANSFER:
            frames = cls._resize_images(frames, size=settings.MAX_FRAME_SIZE_FOR_STYLE_TRANSFER)

        with comixGAN.graph.as_default():
            with comixGAN.session.as_default():
                batch_size = 2
                stylized_imgs = []
                for i in range(0, len(frames), batch_size):
                    batch_of_frames = ((np.stack(frames[i:i + batch_size]) / 255) * 2) - 1
                    stylized_batch_of_imgs = comixGAN.model.predict(batch_of_frames)
                    stylized_imgs.append(255 * ((stylized_batch_of_imgs + 1) / 1.25))

        return list(np.concatenate(stylized_imgs, axis=0))

    @classmethod
    def _cartoon_gan_stylize(cls, frames, gpu=True, style='Hayao'):
        if style == 'Hayao':
            model_cache_key = 'model_cache_hayao'
            model = cache.get(model_cache_key)  # get model from cache

        elif style == 'Hosoda':
            model_cache_key = 'model_cache_hosoda'
            model = cache.get(model_cache_key)  # get model from cache

        else:
            raise Exception('No such CartoonGAN model!')

        if model is None:
            # load pretrained model
            model = Transformer()
            model.load_state_dict(torch.load(os.path.join("CartoonGAN/pretrained_model", style + "_net_G_float.pth")))
            model.eval()
            model.cuda() if gpu else model.float()
            cache.set(model_cache_key, model, None)  # None is the timeout parameter. It means cache forever

        frames = cls._resize_images(frames, size=450)
        stylized_imgs = []
        for img in frames:
            input_image = transforms.ToTensor()(img).unsqueeze(0)

            # preprocess, (-1, 1)
            input_image = -1 + 2 * input_image
            input_image = Variable(input_image).cuda() if gpu else Variable(input_image).float()

            # forward
            output_image = model(input_image)
            output_image = output_image[0]

            # deprocess, (0, 1)
            output_image = (output_image.data.cpu().float() * 0.5 + 0.5).numpy()

            # switch channels -> (c, h, w) -> (h, w, c)
            output_image = np.rollaxis(output_image, 0, 3)

            # append image to result images
            stylized_imgs.append(255 * output_image)

        return stylized_imgs
