#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
This is an example dag for using the Kubernetes Pod Operator.
"""
import os

from airflow import DAG
from libs.helper import print_stuff
from airflow.utils.dates import days_ago
from airflow.contrib.operators.kubernetes_pod_operator import KubernetesPodOperator
from airflow.contrib.kubernetes.volume import Volume
from airflow.contrib.kubernetes.volume_mount import VolumeMount


##
# Persistent Volume Configuration
##

"""
Configuration for PVC claim
claimName (string): Name of the PVC claim in kubernetes
"""
volume_config= {
    'persistentVolumeClaim':
      {
        'claimName': 'airflow1data'
      }
    }

volume = Volume(name='airflow1data', configs=volume_config)

"""
Configuration for Volume Mounting location from PVC
name (string): Name of the PVC volume request
mount_path (string): Mount directory in the pod
sub_path (string): Sub path based on the mount directory
read_only (boolean): If the mount is read only or not
"""
volume_mount = VolumeMount('airflow1data',
                            mount_path='/mnt/azure',
                            sub_path=None,
                            read_only=True)

args = {
    'owner': 'airflow',
    'start_date': days_ago(2)
}

##
# Example DAG
##
with DAG(
    dag_id='kubernetes_pod_operator_example',
    default_args=args,
    schedule_interval=None,
    tags=['example'],
) as dag:

    
    """
    Example Task using KubernetesPodOperator
    This will start up a new Pod(Container) for each instance
    Arguments:
    name (string): Name of the pod for kubernetes
    namespace (string): Name of namespace everything resides in. Default is 'default'
    image (string): Name of the docker image. Defaults to dockerhub but can point to private container registries
    cmds (list): List of strings for commands to run in the container
    arguments (list): List of strings for commands to run in container based on cmds
    volumes (list): List of Volume objects containing which volumes will be mounted
    volume_mounts (list): List of VolumeMount objects containing mount locations to the container
    is_delete_operator_pod (boolean): Delete pod when done. Should be true always.
    """

    
    example_task = KubernetesPodOperator(
        task_id="example",
        name = "kubetest",
        namespace='default',
        image="airflow1.azurecr.io/python:v1",
        cmds=["ls"],
        arguments=["/mnt/azure"],
        volumes=[volume],
        volume_mounts=[volume_mount],
        is_delete_operator_pod=True
    )

    # Order for pipeline to do stuff
    example_task
    
