#!/bin/bash

sudo dnf install -y python pip zsh
pip install protobuf ttkbootstrap
chmod +x *.py
export PS1=gateway:$PS1
zsh

