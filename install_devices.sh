#!/bin/bash

sudo dnf install -y python pip zsh
pip install protobuf ttkbootstrap
chmod +x *.py
export PS1=devices:$PS1
zsh

