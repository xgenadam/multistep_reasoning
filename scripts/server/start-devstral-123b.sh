#/mnt/myraid/workspace/open_source/source_code/AI/llama.cpp/build/bin/llama-server \
#--mlock \
# -m /mnt/myraid/workspace/open_source/source_code/AI/text-generation-webui/user_data/models/Devstral-2-123B-Instruct-2512-Q3_K_M-00001-of-00002.gguf \
#--host 127.0.0.1 \
#--port  8000 \
#--parallel  1 \
#--n-gpu-layers 89 \
#--ctx-size 101072 \
#--batch-size 1024 \
#--ubatch-size 1024 \
#--cache-type-k q8_0 \
#--cache-type-v q8_0 \
#--rope-freq-base 1000000 \
#--split-mode row \
#--threads -1 \
#--threads-batch -1  \
#--flash-attn on



/mnt/myraid/workspace/open_source/source_code/AI/llama.cpp/build/bin/llama-server \
--mlock \
 -m /mnt/myraid/workspace/open_source/source_code/AI/text-generation-webui/user_data/models/Devstral-2-123B-Instruct-2512-Q3_K_M-00001-of-00002.gguf \
--host 127.0.0.1 \
--port  8000 \
--parallel  3 \
--n-gpu-layers 89 \
--ctx-size 241920 \
--batch-size 1024 \
--ubatch-size 1024 \
--cache-type-k q4_0 --cache-type-v q4_0 \
--tensor-split 0.25,0.25,0.25,0.25 \
--rope-freq-base 1000000 \
--cont-batching \
--split-mode row \
--threads -1 \
--threads-batch -1  \
--flash-attn on
