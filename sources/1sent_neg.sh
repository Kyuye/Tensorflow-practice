
job_name=REGAN_1sent_neg_4GPU_$(date +%Y%m%d_%H%M%S)

gcloud ml-engine jobs submit training $job_name \
--package-path=$(pwd)/sources/mintor \
--module-name=mintor.model \
--staging-bucket=gs://jejucamp2017/ \
--region=asia-east1 \
--scale-tier=CUSTOM \
--config=./sources/config_4gpu.yaml \
-- \
--on_cloud=True \
--bucket=jejucamp2017 \
--word_vec_map_file=/dataset/word2vec_map.json \
--log_dir=./logs/ \
--gpu_num=4 \
--task=neg_sent


# job_name=REGAN_1sent_neg_singleGPU_$(date +%Y%m%d_%H%M%S)

# gcloud ml-engine jobs submit training $job_name \
# --package-path=$(pwd)/sources/mintor \
# --module-name=mintor.model_1sent \
# --staging-bucket=gs://jejucamp2017/ \
# --region=europe-west1 \
# --scale-tier=BASIC_GPU \
# -- \
# --on_cloud=True \
# --bucket=jejucamp2017 \
# --word_vec_map_file=/dataset/word2vec_map.json \
# --log_dir=./logs/ \
# --gpu_num=1

# sleep 5 

# job_name=REGAN_1sent_neg_4GPU_$(date +%Y%m%d_%H%M%S)

# gcloud ml-engine jobs submit training $job_name \
# --package-path=$(pwd)/sources/mintor \
# --module-name=mintor.model_1sent \
# --staging-bucket=gs://jejucamp2017/ \
# --region=europe-west1 \
# --scale-tier=CUSTOM \
# --config=./sources/config_4gpu.yaml \
# -- \
# --on_cloud=True \
# --bucket=jejucamp2017 \
# --word_vec_map_file=/dataset/word2vec_map.json \
# --log_dir=./logs/ \
# --gpu_num=4 

# sleep 5


# region list
# asia-east1
# us-east1
# us-central1
# europe-west1


# scale tier list
# BASIC: A single worker instance. This tier is suitable for learning how to use Cloud ML Engine and for experimenting with new models using small datasets.
# STANDARD_1: Many workers and a few parameter servers.
# PREMIUM_1: A large number of workers with many parameter servers.
# BASIC_GPU: A single worker instance with a GPU.
# CUSTOM: custom setting


