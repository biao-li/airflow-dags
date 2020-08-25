"""
RNASeq 3
"""
import os

from airflow import DAG
from datetime import timedelta
from airflow.utils.dates import days_ago
from airflow.contrib.operators.kubernetes_pod_operator import KubernetesPodOperator
from airflow.contrib.kubernetes.volume import Volume
from airflow.contrib.kubernetes.volume_mount import VolumeMount
from airflow.operators.bash_operator import BashOperator
from airflow.operators.dummy_operator import DummyOperator

##
# Persistent Volume Configuration
##


## Reference Volume
input_ref_mount = VolumeMount(name='reference-mount',
                              mount_path='/mnt/references',
                              sub_path=None,
                              read_only=True)
input_ref_volume = Volume(name='reference-mount', configs={'persistentVolumeClaim':{'claimName': 'pvc-references'}})

# Input Data Volume
input_data_mount = VolumeMount(name='input-mount',
                                mount_path='/mnt/data',
                                sub_path=None,
                                read_only=True)
input_data_volume = Volume(name='input-mount', configs={'persistentVolumeClaim':{'claimName': 'pvc-input'}})

# Temp Data Volume
temp_data_mount = VolumeMount(name='temp-mount',
                                mount_path='/mnt/temp',
                                sub_path=None,
                                read_only=False)
temp_data_volume = Volume(name='temp-mount', configs={'persistentVolumeClaim':{'claimName': 'pvc-airflow1datatemp'}})

### Output Volume
output_mount = VolumeMount(name='output-mount',
                            mount_path='/mnt/output',
                            sub_path=None,
                            read_only=False)
output_volume = Volume(name='output-mount', configs={'persistentVolumeClaim':{'claimName': 'pvc-output'}})


args = {
    'owner': 'airflow',
    'email': ['asdpfjsdapofjspofjsdapojfspoj@sdfpojsdfpofjsd.io'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes = 5),
    'start_date': days_ago(2)
}


##
# RNA Seq 3
##
with DAG(
    dag_id='rnaseq3',
    default_args=args,
    schedule_interval=None,
    tags=['example'],
) as dag:

    # Parse main file name without extensions
    parse_filename = BashOperator(
            task_id = 'parse_filename',
            bash_command = "filename={{ dag_run.conf['read1_name'] }}; echo ${filename%%.*}",
            xcom_push = True
    )

    # Move to temp Azure File folder for processing
    create_temp = KubernetesPodOperator(
        task_id="create_temp",
        name = "rnaseq2_create_temp_dir",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["/bin/bash"],
        arguments=["-c","printf '{\"dir\": \"%s\"}' $(mktemp -d -p /mnt/temp) > /airflow/xcom/return.json"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '50m', 'request_memory': '50Mi'},
        is_delete_operator_pod=True,
        do_xcom_push = True
    )
    
    ## Move to temp Azure File folder for processing
    #move_temp_in = KubernetesPodOperator(
    #    task_id="move_data_in",
    #    name = "rnaseq2_move_data_to_filesystem",
    #    namespace='default',
    #    image="ubuntu:18.04",
    #    cmds=["cp"],
    #    arguments=["/mnt/data/{{ dag_run.conf['read1_name'] }}", 
    #    "/mnt/data/{{ dag_run.conf['read2_name'] }}", 
    #    "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}"],
    #    volumes=[input_data_volume, temp_data_volume],
    #    volume_mounts=[input_data_mount, temp_data_mount],
    #    resources = {'request_cpu': '2', 'request_memory': '20Gi'},
    #    is_delete_operator_pod=True
    #)

    # Create base folder for sample
    create_base_output_dir = KubernetesPodOperator(
        task_id="create_output_dir",
        name = "rnaseq2_create_output_dir",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["mkdir"],
        arguments=["{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '50m', 'request_memory': '50Mi'},
        is_delete_operator_pod=True
    )    

    # STAR
    ## Create star empty directory
    create_star_dir = KubernetesPodOperator(
        task_id="create_star_directory",
        name = "rnaseq2_create_star_dir",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["mkdir"],
        arguments=["{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/star"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '50m', 'request_memory': '50Mi'},
        is_delete_operator_pod=True
    )

    ## STAR
    run_star = KubernetesPodOperator(
        task_id="run_star",
        name = "rnaseq2_star",
        namespace='default',
        image="quay.io/biocontainers/star:2.7.3a--0",
        cmds=["/usr/local/bin/STAR"], 
        arguments = ["--genomeDir", "/mnt/references/ref/star_gencode_v33_index", 
        "--runThreadN", "7",
        "--readFilesCommand", "zcat", 
        "--readFilesIn", "/mnt/data/{{ dag_run.conf['read1_name'] }}", "/mnt/data/{{ dag_run.conf['read2_name'] }}", 
        "--outFileNamePrefix", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/star/",
        "--outSAMunmapped", "Within",
        "--outSAMtype", "BAM", "SortedByCoordinate",
        "--quantMode", "TranscriptomeSAM", "GeneCounts"],
        volumes=[input_ref_volume, input_data_volume, temp_data_volume],
        volume_mounts=[input_ref_mount, input_data_mount, temp_data_mount],
        resources = {'request_cpu': '7000m', 'request_memory': '29Gi'},
        is_delete_operator_pod=True
    )

    # SALMON
    ## Create salmon empty directory
    create_salmon_dir = KubernetesPodOperator(
        task_id="create_salmon_directory",
        name = "rnaseq2_create_salmon_dir",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["mkdir"],
        arguments=["{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/salmon"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '50m', 'request_memory': '50Mi'},
        is_delete_operator_pod=True
    )

    ## SALMON
    run_salmon = KubernetesPodOperator(
        task_id="run_salmon",
        name = "rnaseq2_salmon",
        namespace='default',
        image="combinelab/salmon:1.2.1",
        cmds=["salmon"],
        arguments=["quant",
        "-i", "/mnt/references/ref/salmon_gencode_v33_index", 
        "-l", "A", 
        "-1", "/mnt/data/{{ dag_run.conf['read1_name'] }}", 
        "-2", "/mnt/data/{{ dag_run.conf['read2_name'] }}",
        "-p", "7",
        "-g", "/mnt/references/ref/gencode.v33.annotation.gtf",
        "-o", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/salmon"],
        volumes=[input_ref_volume, input_data_volume, temp_data_volume],
        volume_mounts=[input_ref_mount, input_data_mount, temp_data_mount],
        resources = {'request_cpu': '7000m', 'request_memory': '29Gi'},
        is_delete_operator_pod=True
    )

    # FastQC
    ## Create fastqc empty directory
    create_fastqc_dir = KubernetesPodOperator(
        task_id="create_fastqc_directory",
        name = "rnaseq2_create_fastqc_dir",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["mkdir"],
        arguments=["{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/fastqc"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '50m', 'request_memory': '50Mi'},
        is_delete_operator_pod=True
    )

    ## Run FastQC
    run_fastqc = KubernetesPodOperator(
        task_id="run_fastqc",
        name = "rnaseq2_fastqc",
        namespace='default',
        image="quay.io/biocontainers/fastqc:0.11.9--0",
        cmds=["fastqc"],
        arguments=["/mnt/data/{{ dag_run.conf['read1_name'] }}",
        "/mnt/data/{{ dag_run.conf['read2_name'] }}",
        "-o", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/fastqc",
        "-t", "1"
        ],
        volumes=[input_data_volume, temp_data_volume],
        volume_mounts=[input_data_mount, temp_data_mount],
        resources = {'request_cpu': '1'},
        is_delete_operator_pod=True
    )

    # Samtools sort
    run_samtools = KubernetesPodOperator(
        task_id="run_samtools_sort",
        name = "rnaseq2_samtools",
        namespace='default',
        image="quay.io/biocontainers/samtools:1.3--h0592bc0_3",
        cmds=["samtools"],
        arguments=["sort",
        "-n",
        "-o", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/out.sortedByName.bam",
        "-m", "7G",
        "-@", "$(nproc)",
        "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/star/Aligned.sortedByCoord.out.bam"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_memory': '7Gi', 'request_cpu': '1'},
        is_delete_operator_pod=True
    )

    # Qualimap
    ## Create qualimap empty directory
    create_qualimap_dir = KubernetesPodOperator(
        task_id="create_qualimap_directory",
        name = "rnaseq2_create_qualimap_dir",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["mkdir"],
        arguments=["{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/qualimap"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '50m', 'request_memory': '50Mi'},
        is_delete_operator_pod=True
    )

    ## Qualimap
    run_qualimap = KubernetesPodOperator(
        task_id="run_qualimap",
        name = "rnaseq2_qualimap",
        namespace='default',
        image="quay.io/biocontainers/qualimap:2.2.2d--1",
        cmds=["qualimap"], 
        arguments=["rnaseq",
        "-bam", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/out.sortedByName.bam",
        "-gtf", "/mnt/references/ref/gencode.v33.annotation.gtf",
        "--java-mem-size=60G",
        "-pe",
        "-s", "-outdir", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/qualimap"],
        volumes=[input_ref_volume, temp_data_volume],
        volume_mounts=[input_ref_mount, temp_data_mount],
        resources = {'request_cpu': '6', 'request_memory': '29Gi'},
        is_delete_operator_pod=True
    )

    # GATK
    ## Create GATK tmp directory
    create_gatk_dir = KubernetesPodOperator(
        task_id="create_gatk_directory",
        name = "rnaseq2_create_gatk_dir",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["mkdir"],
        arguments=["{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/tmp"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '50m', 'request_memory': '50Mi'},
        is_delete_operator_pod=True
    )

    ## Run GATK
    run_gatk = KubernetesPodOperator(
        task_id="run_gatk",
        name = "rnaseq2_gatk",
        namespace='default',
        image="broadinstitute/gatk:4.1.7.0",
        cmds=["gatk"],
        arguments=["--java-options", "-Xmx7G",
        "EstimateLibraryComplexity",
        "-I", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/star/Aligned.sortedByCoord.out.bam",
        "-O", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/gatk",
        #"-pe",
        "--TMP_DIR", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/tmp"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '7000m', 'request_memory': '8Gi'},
        is_delete_operator_pod=True
    )

    # rseqc
    ## Create rseqc empty directory
    create_rseqc_dir = KubernetesPodOperator(
        task_id="create_rseqc_directory",
        name = "rnaseq2_create_rseqc_dir",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["mkdir"],
        arguments=["{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/rseqc"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '50m', 'request_memory': '100Mi'},
        is_delete_operator_pod=True
    )

    ## Run Rseqc
    run_rseqc = KubernetesPodOperator(
        task_id="run_rseqc",
        name = "rnaseq2_rseqc",
        namespace='default',
        image="quay.io/biocontainers/rseqc:3.0.1--py37h516909a_1",
        cmds=["geneBody_coverage.py"],
        arguments=["-r", "/mnt/references/ref/gencode.v33.annotation.bed",
        "-i", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/star/Aligned.sortedByCoord.out.bam",
        "-o", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}/rseqc/{{ti.xcom_pull(task_ids = 'parse_filename')}}"],
        volumes=[input_ref_volume, temp_data_volume],
        volume_mounts=[input_ref_mount, temp_data_mount],
        is_delete_operator_pod=True
    )

    # Move data after done processing to long term blob storage
    copy_data_to_storage = KubernetesPodOperator(
        task_id="copy_data_to_storage",
        name = "rnaseq2_upload_to_storage",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["cp"],
        arguments=["-r", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}/{{ti.xcom_pull(task_ids = 'parse_filename')}}", "/mnt/output"],
        volumes=[temp_data_volume, output_volume],
        volume_mounts=[temp_data_mount, output_mount],
        resources = {'request_cpu': '2', 'request_memory': '20Gi'},
        is_delete_operator_pod=True
    )

    # Delete file share temp data
    cleanup_temp = KubernetesPodOperator(
        task_id="cleanup_temp",
        name = "rnaseq2_cleanup_temp",
        namespace='default',
        image="ubuntu:18.04",
        cmds=["rm"],
        arguments=["-rf", "{{ti.xcom_pull(task_ids = 'create_temp')['dir']}}"],
        volumes=[temp_data_volume],
        volume_mounts=[temp_data_mount],
        resources = {'request_cpu': '1', 'request_memory': '1Gi'},
        is_delete_operator_pod=True
    )

    ## Dummies
    do_alignments = DummyOperator(
        task_id = "do_alignments"
    )

    do_qc_and_quantification = DummyOperator(
        task_id = "do_qc_and_quantification"
    )

    be_done = DummyOperator(
        task_id = "done"
    )

    start = DummyOperator(
        task_id = "start"
    )

    #parse_filename >> create_base_output_dir >> create_star_dir >> run_star >> create_salmon_dir >> run_salmon >> create_fastqc_dir >> run_fastqc >> run_samtools >> create_qualimap_dir >> run_qualimap >> create_gatk_dir >> run_gatk >> create_rseqc_dir >> run_rseqc
    start >> [parse_filename, create_temp] >> create_base_output_dir >> [create_star_dir, create_salmon_dir, create_fastqc_dir, create_qualimap_dir, create_gatk_dir, create_rseqc_dir] >> do_alignments >> [run_star, run_fastqc] >> do_qc_and_quantification >> [run_rseqc, run_samtools, run_gatk, run_salmon]  >> run_qualimap >> copy_data_to_storage >> cleanup_temp >> be_done