import functools
import os
import tempfile
import diffusers
import gradio as gr
import imageio as imageio
import numpy as np
import spaces
import torch
from PIL import Image
from tqdm import tqdm
from pathlib import Path
from pipeline import LotusGPipeline, LotusDPipeline
from utils.image_utils import colorize_depth_map
from contextlib import nullcontext
import cv2

import gradio
from gradio.utils import get_cache_folder
import transformers
from gradio_imageslider import ImageSlider

import sys

transformers.utils.move_cache()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def infer_pipe(pipe, image_input, task_name, seed, device):
    if seed is None:
        generator = None
    else:
        generator = torch.Generator(device=device).manual_seed(seed)

    if torch.backends.mps.is_available():
        autocast_ctx = nullcontext()
    else:
        autocast_ctx = torch.autocast(pipe.device.type)
    with autocast_ctx:

        test_image = Image.open(image_input).convert('RGB')
        test_image = np.array(test_image).astype(np.float16)
        test_image = torch.tensor(test_image).permute(2,0,1).unsqueeze(0)
        test_image = test_image / 127.5 - 1.0 
        test_image = test_image.to(device)

        task_emb = torch.tensor([1, 0]).float().unsqueeze(0).repeat(1, 1).to(device)
        task_emb = torch.cat([torch.sin(task_emb), torch.cos(task_emb)], dim=-1).repeat(1, 1)

        # Run
        pred = pipe(
            rgb_in=test_image, 
            prompt='', 
            num_inference_steps=1, 
            generator=generator, 
            # guidance_scale=0,
            output_type='np',
            timesteps=[999],
            task_emb=task_emb,
            ).images[0]

        # Post-process the prediction
        if task_name == 'depth':
            output_npy = pred.mean(axis=-1)
            output_color = colorize_depth_map(output_npy)
        else:
            output_npy = pred
            output_color = Image.fromarray((output_npy * 255).astype(np.uint8))

    return output_color

def lotus_video(input_video, task_name, seed, device):
    if task_name == 'depth':
        model_g = 'jingheya/lotus-depth-g-v1-0'
        model_d = 'jingheya/lotus-depth-d-v1-0'
    else:
        model_g = 'jingheya/lotus-normal-g-v1-0'
        model_d = 'jingheya/lotus-normal-d-v1-0'

    dtype = torch.float16
    pipe_g = LotusGPipeline.from_pretrained(
        model_g,
        torch_dtype=dtype,
    )
    pipe_d = LotusDPipeline.from_pretrained(
        model_d,
        torch_dtype=dtype,
    )
    pipe_g.to(device)
    pipe_d.to(device)
    pipe_g.set_progress_bar_config(disable=True)
    pipe_d.set_progress_bar_config(disable=True)
    # logging.info(f"Successfully loading pipeline from {model_g} and {model_d}.")
    
    # load the video and split it into frames
    cap = cv2.VideoCapture(input_video)
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()
    # logging.info(f"There are {len(frames)} frames in the video.")

    if seed is None:
        generator = None
    else:
        generator = torch.Generator(device=device).manual_seed(seed)

    task_emb = torch.tensor([1, 0]).float().unsqueeze(0).repeat(1, 1).to(device)
    task_emb = torch.cat([torch.sin(task_emb), torch.cos(task_emb)], dim=-1).repeat(1, 1)

    output_g = []
    output_d = []
    for frame in frames:
        if torch.backends.mps.is_available():
            autocast_ctx = nullcontext()
        else:
            autocast_ctx = torch.autocast(pipe_g.device.type)
        with autocast_ctx:
            test_image = frame
            test_image = np.array(test_image).astype(np.float16)
            test_image = torch.tensor(test_image).permute(2,0,1).unsqueeze(0)
            test_image = test_image / 127.5 - 1.0 
            test_image = test_image.to(device)

            # Run
            pred_g = pipe_g(
                rgb_in=test_image, 
                prompt='', 
                num_inference_steps=1, 
                generator=generator, 
                # guidance_scale=0,
                output_type='np',
                timesteps=[999],
                task_emb=task_emb,
                ).images[0]
            pred_d = pipe_d(
                rgb_in=test_image, 
                prompt='', 
                num_inference_steps=1, 
                generator=generator, 
                # guidance_scale=0,
                output_type='np',
                timesteps=[999],
                task_emb=task_emb,
                ).images[0]

            # Post-process the prediction
            if task_name == 'depth':
                output_npy_g = pred_g.mean(axis=-1)
                output_color_g = colorize_depth_map(output_npy_g)
                output_npy_d = pred_d.mean(axis=-1)
                output_color_d = colorize_depth_map(output_npy_d)
            else:
                output_npy_g = pred_g
                output_color_g = Image.fromarray((output_npy_g * 255).astype(np.uint8))
                output_npy_d = pred_d
                output_color_d = Image.fromarray((output_npy_d * 255).astype(np.uint8))
            
            output_g.append(output_color_g)
            output_d.append(output_color_d)

    return output_g, output_d

def lotus(image_input, task_name, seed, device):
    if task_name == 'depth':
        model_g = 'jingheya/lotus-depth-g-v1-0'
        model_d = 'jingheya/lotus-depth-d-v1-1'
    else:
        model_g = 'jingheya/lotus-normal-g-v1-0'
        model_d = 'jingheya/lotus-normal-d-v1-0'

    dtype = torch.float16
    pipe_g = LotusGPipeline.from_pretrained(
        model_g,
        torch_dtype=dtype,
    )
    pipe_d = LotusDPipeline.from_pretrained(
        model_d,
        torch_dtype=dtype,
    )
    pipe_g.to(device)
    pipe_d.to(device)
    pipe_g.set_progress_bar_config(disable=True)
    pipe_d.set_progress_bar_config(disable=True)
    # logging.info(f"Successfully loading pipeline from {model_g} and {model_d}.")
    output_g = infer_pipe(pipe_g, image_input, task_name, seed, device)
    output_d = infer_pipe(pipe_d, image_input, task_name, seed, device)
    return output_g, output_d

def infer(path_input, seed):
    name_base, name_ext = os.path.splitext(os.path.basename(path_input))
    output_g, output_d = lotus(path_input, TASK, seed, device)
    if not os.path.exists(f"assets/app/{TASK}/output"):
        os.makedirs(f"assets/app/{TASK}/output")
    g_save_path = os.path.join(f"assets/app/{TASK}/output", f"{name_base}_g{name_ext}")
    d_save_path = os.path.join(f"assets/app/{TASK}/output", f"{name_base}_d{name_ext}")
    output_g.save(g_save_path)
    output_d.save(d_save_path)
    return [path_input, g_save_path], [path_input, d_save_path]

def infer_video(path_input, seed):
    frames_g, frames_d = lotus_video(path_input, TASK, seed, device)
    if not os.path.exists(f"assets/app/{TASK}/output"):
        os.makedirs(f"assets/app/{TASK}/output")
    name_base, _ = os.path.splitext(os.path.basename(path_input))
    g_save_path = os.path.join(f"assets/app/{TASK}/output", f"{name_base}_g.mp4")
    d_save_path = os.path.join(f"assets/app/{TASK}/output", f"{name_base}_d.mp4")
    imageio.mimsave(g_save_path, frames_g)
    imageio.mimsave(d_save_path, frames_d)
    return [g_save_path, d_save_path]

def run_demo_server():
    infer_gpu = spaces.GPU(functools.partial(infer))
    infer_video_gpu = spaces.GPU(functools.partial(infer_video))
    gradio_theme = gr.themes.Default()

    with gr.Blocks(
        theme=gradio_theme,
        title=f"LOTUS - {TASK.capitalize()}",
        css="""
            #download {
                height: 118px;
            }
            .slider .inner {
                width: 5px;
                background: #FFF;
            }
            .viewport {
                aspect-ratio: 4/3;
            }
            .tabs button.selected {
                font-size: 20px !important;
                color: crimson !important;
            }
            h1 {
                text-align: center;
                display: block;
            }
            h2 {
                text-align: center;
                display: block;
            }
            h3 {
                text-align: center;
                display: block;
            }
            .md_feedback li {
                margin-bottom: 0px !important;
            }
        """,
        head="""
            <script async src="https://www.googletagmanager.com/gtag/js?id=G-1FWSVCGZTG"></script>
            <script>
                window.dataLayer = window.dataLayer || [];
                function gtag() {dataLayer.push(arguments);}
                gtag('js', new Date());
                gtag('config', 'G-1FWSVCGZTG');
            </script>
        """,
    ) as demo:
        gr.Markdown(
            """
            # LOTUS: Diffusion-based Visual Foundation Model for High-quality Dense Prediction
            <p align="center">
            <a title="Page" href="https://lotus3d.github.io/" target="_blank" rel="noopener noreferrer" style="display: inline-block;">
                <img src="https://img.shields.io/badge/Project-Website-pink?logo=googlechrome&logoColor=white">
            </a>
            <a title="arXiv" href="https://arxiv.org/abs/2409.18124" target="_blank" rel="noopener noreferrer" style="display: inline-block;">
                <img src="https://img.shields.io/badge/arXiv-Paper-b31b1b?logo=arxiv&logoColor=white">
            </a>
            <a title="Github" href="https://github.com/EnVision-Research/Lotus" target="_blank" rel="noopener noreferrer" style="display: inline-block;">
                <img src="https://img.shields.io/github/stars/EnVision-Research/Lotus?label=GitHub%20%E2%98%85&logo=github&color=C8C" alt="badge-github-stars">
            </a>
            <a title="Social" href="https://x.com/haodongli00/status/1839524569058582884" target="_blank" rel="noopener noreferrer" style="display: inline-block;">
                <img src="https://www.obukhov.ai/img/badges/badge-social.svg" alt="social">
            </a>
        """
        )
        with gr.Tabs(elem_classes=["tabs"]):
            with gr.Tab("IMAGE"):
                with gr.Row():
                    with gr.Column():
                        image_input = gr.Image(
                            label="Input Image",
                            type="filepath",
                        )
                        seed = gr.Number(
                            label="Seed (only for Generative mode)",
                            minimum=0,
                            maximum=999999999,
                        )
                        with gr.Row():
                            image_submit_btn = gr.Button(
                                value=f"Predict {TASK.capitalize()}!", variant="primary"
                            )
                            image_reset_btn = gr.Button(value="Reset")
                    with gr.Column():
                        image_output_g = ImageSlider(
                            label="Output (Generative)",
                            type="filepath",
                            interactive=False,
                            elem_classes="slider",
                            position=0.25,
                        )
                        with gr.Row():
                            image_output_d = ImageSlider(
                                label="Output (Discriminative)",
                                type="filepath",
                                interactive=False,
                                elem_classes="slider",
                                position=0.25,
                            )

                gr.Examples(
                    fn=infer_gpu,
                    examples=sorted([
                        [os.path.join(f"assets/app/{TASK}", "images", name), 0]
                        for name in os.listdir(os.path.join(f"assets/app/{TASK}", "images"))
                    ]),
                    inputs=[image_input, seed],
                    outputs=[image_output_g, image_output_d],
                    cache_examples=False,
                )

            with gr.Tab("VIDEO"):
                with gr.Row():
                    with gr.Column():
                        input_video = gr.Video(
                            label="Input Video",
                            autoplay=True,
                            loop=True,
                        )
                        seed = gr.Number(
                            label="Seed (only for Generative mode)",
                            minimum=0,
                            maximum=999999999,
                        )
                        with gr.Row():
                            video_submit_btn = gr.Button(
                                value=f"Predict {TASK.capitalize()}!", variant="primary"
                            )
                            video_reset_btn = gr.Button(value="Reset")
                    with gr.Column():
                        video_output_g = gr.Video(
                            label="Output (Generative)",
                            interactive=False,
                            autoplay=True,
                            loop=True,
                            show_share_button=True,
                        )
                        with gr.Row():
                            video_output_d = gr.Video(
                                label="Output (Discriminative)",
                                interactive=False,
                                autoplay=True,
                                loop=True,
                                show_share_button=True,
                            )

                gr.Examples(
                    fn=infer_video_gpu,
                    examples=sorted([
                        [os.path.join(f"assets/app/{TASK}", "videos", name), 0]
                        for name in os.listdir(os.path.join(f"assets/app/{TASK}", "videos"))
                    ]),
                    inputs=[input_video, seed],
                    outputs=[video_output_g, video_output_d],
                    cache_examples=False,
                )

        ### Image
        image_submit_btn.click(
            fn=infer_gpu,
            inputs=[image_input, seed],
            outputs=[image_output_g, image_output_d],
            concurrency_limit=1,
        )
        image_reset_btn.click(
            fn=lambda: (
                None,
                None,
                None,
            ),
            inputs=[],
            outputs=[image_output_g, image_output_d],
            queue=False,
        )

        ### Video
        video_submit_btn.click(
            fn=infer_video_gpu,
            inputs=[input_video, seed],
            outputs=[video_output_g, video_output_d],
            queue=True,
        )
        video_reset_btn.click(
            fn=lambda: (None, None, None),
            inputs=[],
            outputs=[video_output_g, video_output_d],
        )

        ### Server launch
        demo.queue(
            api_open=False,
        ).launch(
            server_name="0.0.0.0",
            server_port=7860,
        )

def main():
    os.system("pip freeze")
    if os.path.exists("files/output"):
        os.system("rm -rf files/output")
    run_demo_server()

if __name__ == "__main__":
    TASK = sys.argv[-1]
    if not TASK in ['depth', 'normal']:
        raise ValueError("Invalid task. Please choose from 'depth' and 'normal'.")
    main()