# -*- coding: utf-8 -*-
"""Copy of t5-trivia

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1DDn-D-0e57hlfCQIzIT9QVGN9K_5yFqk

<a href="https://colab.research.google.com/github/google-research/text-to-text-transfer-transformer/blob/master/notebooks/t5-trivia.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a>

##### Copyright 2019 The T5 Authors

Licensed under the Apache License, Version 2.0 (the "License");
"""

# Copyright 2019 The T5 Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""# Fine-Tuning the Text-To-Text Transfer Transformer (T5) for Closed-Book Question Answering
## _Or: What does T5 know?_

*The following tutorial guides you through the process of fine-tuning a pre-trained T5 model, evaluating its accuracy, and using it for prediction,
all on a free Google Cloud TPU <a href="https://colab.research.google.com/github/google-research/text-to-text-transfer-transformer/blob/master/notebooks/t5-trivia.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a>.*

### Background

T5 was introduced in the paper [_Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer_](https://arxiv.org/abs/1910.10683). In that paper, we provided a comprehensive picture of how we pre-trained a standard text-to-text Transformer model on a large text corpus, achieving state-of-the-art results on many NLP tasks after fine-tuning.

We pre-trained T5 on a mixture of supervised and unsupervised tasks with the majoriy of data coming from an unlabeled dataset we developed called [C4](https://www.tensorflow.org/datasets/catalog/c4). C4 is based on a massive scrape of the web produced by [Common Crawl](https://commoncrawl.org). Loosely speaking, pre-training on C4 ideally gives T5 an understanding of natural language in addition to general world knowledge.

### How can we assess what T5 knows?

As the name implies, T5 is a text-to-text model, which enables us to train it on arbitrary tasks involving a textual input and output. As we showed in our paper, a huge variety of NLP tasks can be cast in this format, including translation, summarization, and even classification and regression tasks.

One way to use this text-to-text framework is on reading comprehension problems, where the model is fed some context along with a question and is trained to predict the question's answer. For example, we might feed the model the text from the Wikipedia article about [Hurrican Connie](https://en.wikipedia.org/wiki/Hurricane_Connie) along with the question "On what date did Hurricane Connie occur?" and train the model to predict the answer "August 3rd, 1955".
A related task is open-domain question answering (QA) where the model is not provided with this oracle context. Typically, open-domain QA systems include a mechanism to look up information in an external knowledge source. This setting is similar to an "open-book" exam.

In this notebook, we'll be training T5 on a variant of this task which we call **closed-book question answering**. In closed-book QA, we feed the model a question *without any context or access to external knowledge* and train it to predict the answer. Since the model doesn't receive any context, the primary way it can learn to answer these questions is based on the "knowledge" it obtained during pre-training. We don't expect T5 to contain super specific information, so we will be focusing on two question-answering datasets which largely include trivia questions (i.e. facts about well-known subjects). [Similar](https://arxiv.org/abs/1909.01066) [investigations](https://d4mucfpksywv.cloudfront.net/better-language-models/language_models_are_unsupervised_multitask_learners.pdf) have recently been done to test the knowledge stored by BERT and GPT-2.

T5 was not pre-trained on closed-book QA, so in this notebook we'll first create two new tasks and then use the [`t5`](https://github.com/google-research/text-to-text-transfer-transformer) library to fine-tune, evaluate, and obtain predictions from T5. In the end, T5's performance on closed-book QA can give us a sense of what kind (and how much) information T5 managed to learn during pre-training.

We published a [more in-depth investigation](https://tiny.cc/t5-qa) of closed-book QA with T5 where we achieved suprisingly strong performance on open-domain variants of Natural Questions, WebQuestions, and TriviaQA. The code in this notebook is a simplified version of those experiments but still produces good results.


### Caveats

* While we provide instructions for running on a [Cloud TPU](https://cloud.google.com/tpu/) via Colab for free, a [Google Cloud Storage (GCS)](http://console.cloud.google.com/storage) bucket is required for storing model parameters and data. The [GCS free tier](https://cloud.google.com/free/) provides 5 GB of storage, which should be enough to train the `large` model and smaller but not the `3B` or `11B` parameter models. You can use part of your initial $300 credit to get more space.
* The Cloud TPU provided by Colab (a `v2-8`) does not have enough memory to fine-tune the `11B` parameter model. For this model, you will need to fine-tune inside of a GCP instance (see [README](https://github.com/google-research/text-to-text-transfer-transformer/)).

# Set Up

<h3><a href="https://cloud.google.com/tpu/"><img valign="middle" src="https://raw.githubusercontent.com/GoogleCloudPlatform/tensorflow-without-a-phd/master/tensorflow-rl-pong/images/tpu-hexagon.png" width="50"></a>  &nbsp;&nbsp;Train on TPU</h3>




   1. Create a Cloud Storage bucket for your data and model checkpoints at http://console.cloud.google.com/storage, and fill in the `BASE_DIR` parameter in the following form. There is a [free tier](https://cloud.google.com/free/) if you do not yet have an account.

   1. On the main menu, click Runtime and select **Change runtime type**. Set "TPU" as the hardware accelerator.
   1. Run the following cell and follow instructions to:
    *  Set up a Colab TPU running environment
    *   Verify that you are connected to a TPU device
    *   Upload your credentials to TPU to access your GCS bucket
"""

# Commented out IPython magic to ensure Python compatibility.
# TODO(adarob): Add support for 2.x.
# %tensorflow_version 1.x

import datetime
import functools
import json
import os
import pprint
import random
import string
import sys
import tensorflow as tf

BASE_DIR = "gs://base"  # @param { type: "string" }
if not BASE_DIR or BASE_DIR == "gs://":
    raise ValueError("You must enter a BASE_DIR.")
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "models")
ON_CLOUD = True

if ON_CLOUD:
    assert "COLAB_TPU_ADDR" in os.environ, "ERROR: Not connected to a TPU runtime; please see the first cell in this notebook for instructions!"
    TPU_ADDRESS = "grpc://" + os.environ["COLAB_TPU_ADDR"]
    TPU_TOPOLOGY = "2x2"
    print("TPU address is", TPU_ADDRESS)

    from google.colab import auth

    auth.authenticate_user()
    with tf.Session(TPU_ADDRESS) as session:
        print('TPU devices:')
        pprint.pprint(session.list_devices())

        # Upload credentials to TPU.
        with open('/content/adc.json', 'r') as f:
            auth_info = json.load(f)
        tf.contrib.cloud.configure_gcs(session, credentials=auth_info)
        # Now credentials are set for all future sessions on this TPU.

# @title Install and import required packages
if ON_CLOUD:
    !pip
    install - qU
    t5

import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import t5
import tensorflow as tf
import tensorflow_datasets as tfds
import time

# Improve logging.
from contextlib import contextmanager
import logging as py_logging

if ON_CLOUD:
    tf.get_logger().propagate = False
    py_logging.root.setLevel('INFO')


@contextmanager
def tf_verbosity_level(level):
    og_level = tf.logging.get_verbosity()
    tf.logging.set_verbosity(level)
    yield
    tf.logging.set_verbosity(og_level)


"""# Creating new Tasks and Mixture

Two core components of the T5 library are `Task` and `Mixture` objects.

A `Task` is a dataset along with preprocessing functions and evaluation metrics. A `Mixture` is a collection of `Task` objects along with a mixing rate or a function defining how to compute a mixing rate based on the properties of the constituent `Tasks`.

For this example, we will fine-tune the model to do closed-book question answering.

### Natural Questions

[Natural Questions (NQ)](https://ai.google.com/research/NaturalQuestions) is a challenging corpus for open-domain QA. Each example includes a question along with an entire Wikipedia article that may or may not contain its answer. The goal is to produce the correct answer given this context. In our case, we will be ignoring the provided context in hopes that the model will learn to find the answers from the world knowledge it has acquired during pre-training.

Since the raw data splits are stored as JSONL files, we will first need to convert them to TSV format to make them parseable in TensorFlow. We will also take the opportunity to drop information we will not be using, remove questions with multiple answers, and to do a bit of cleaning of the text.
"""

import gzip
import json
import os

# Public directory of Natural Questions data on GCS.
NQ_JSONL_DIR = "gs://natural_questions/v1.0-simplified/"
NQ_SPLIT_FNAMES = {
    "train": "simplified-nq-train.jsonl.gz",
    "validation": "nq-dev-all.jsonl.gz"
}
nq_counts_path = os.path.join(DATA_DIR, "nq-counts.json")
nq_tsv_path = {
    "train": os.path.join(DATA_DIR, "nq-train.tsv"),
    "validation": os.path.join(DATA_DIR, "nq-validation.tsv")
}


def nq_jsonl_to_tsv(in_fname, out_fname):
    def extract_answer(tokens, span):
        """Reconstruct answer from token span and remove extra spaces."""
        start, end = span["start_token"], span["end_token"]
        ans = " ".join(tokens[start:end])
        # Remove incorrect spacing around punctuation.
        ans = ans.replace(" ,", ",").replace(" .", ".").replace(" %", "%")
        ans = ans.replace(" - ", "-").replace(" : ", ":").replace(" / ", "/")
        ans = ans.replace("( ", "(").replace(" )", ")")
        ans = ans.replace("`` ", "\"").replace(" ''", "\"")
        ans = ans.replace(" 's", "'s").replace("s ' ", "s' ")
        return ans

    count = 0
    with tf.io.gfile.GFile(in_fname, "rb") as infile, \
            tf.io.gfile.GFile(out_fname, "w") as outfile:
        for line in gzip.open(infile):
            ex = json.loads(line)
            # Remove any examples with more than one answer.
            if len(ex['annotations'][0]['short_answers']) != 1:
                continue
            # Questions in NQ do not include a question mark.
            question = ex["question_text"] + "?"
            answer_span = ex['annotations'][0]['short_answers'][0]
            # Handle the two document formats in NQ (tokens or text).
            if "document_tokens" in ex:
                tokens = [t["token"] for t in ex["document_tokens"]]
            elif "document_text" in ex:
                tokens = ex["document_text"].split(" ")
            answer = extract_answer(tokens, answer_span)
            # Write this line as <question>\t<answer>
            outfile.write("%s\t%s\n" % (question, answer))
            count += 1
            tf.logging.log_every_n(
                tf.logging.INFO,
                "Wrote %d examples to %s." % (count, out_fname),
                1000)
        return count


if tf.io.gfile.exists(nq_counts_path):
    # Used cached data and counts.
    tf.logging.info("Loading NQ from cache.")
    num_nq_examples = json.load(tf.io.gfile.GFile(nq_counts_path))
else:
    # Create TSVs and get counts.
    tf.logging.info("Generating NQ TSVs.")
    num_nq_examples = {}
    for split, fname in NQ_SPLIT_FNAMES.items():
        num_nq_examples[split] = nq_jsonl_to_tsv(
            os.path.join(NQ_JSONL_DIR, fname), nq_tsv_path[split])
    json.dump(num_nq_examples, tf.io.gfile.GFile(nq_counts_path, "w"))

"""Next, we define a function to load the TSV data as a `tf.data.Dataset` in TensorFlow."""


def nq_dataset_fn(split, shuffle_files=False):
    # We only have one file for each split.
    del shuffle_files

    # Load lines from the text file as examples.
    ds = tf.data.TextLineDataset(nq_tsv_path[split])
    # Split each "<question>\t<answer>" example into (question, answer) tuple.
    ds = ds.map(
        functools.partial(tf.io.decode_csv, record_defaults=["", ""],
                          field_delim="\t", use_quote_delim=False),
        num_parallel_calls=tf.data.experimental.AUTOTUNE)
    # Map each tuple to a {"question": ... "answer": ...} dict.
    ds = ds.map(lambda *ex: dict(zip(["question", "answer"], ex)))
    return ds


print("A few raw validation examples...")
for ex in tfds.as_numpy(nq_dataset_fn("validation").take(5)):
    print(ex)

"""Now, we write a preprocess function to convert the examples in the `tf.data.Dataset` into a text-to-text format, with both `inputs` and `targets` fields. The preprocessor also normalizes the text by lowercasing it and removing quotes since the answers are sometimes formatted in odd ways. Finally, we prepend 'trivia question:' to the inputs so that the model knows what task it's trying to solve."""


def trivia_preprocessor(ds):
    def normalize_text(text):
        """Lowercase and remove quotes from a TensorFlow string."""
        text = tf.strings.lower(text)
        text = tf.strings.regex_replace(text, "'(.*)'", r"\1")
        return text

    def to_inputs_and_targets(ex):
        """Map {"question": ..., "answer": ...}->{"inputs": ..., "targets": ...}."""
        return {
            "inputs":
                tf.strings.join(
                    ["trivia question: ", normalize_text(ex["question"])]),
            "targets": normalize_text(ex["answer"])
        }

    return ds.map(to_inputs_and_targets,
                  num_parallel_calls=tf.data.experimental.AUTOTUNE)


"""Finally, we put everything together to create a `Task`."""

t5.data.TaskRegistry.add(
    "nq_context_free",
    # Supply a function which returns a tf.data.Dataset.
    dataset_fn=nq_dataset_fn,
    splits=["train", "validation"],
    # Supply a function which preprocesses text from the tf.data.Dataset.
    text_preprocessor=[trivia_preprocessor],
    # Use the same vocabulary that we used for pre-training.
    sentencepiece_model_path=t5.data.DEFAULT_SPM_PATH,
    # Lowercase targets before computing metrics.
    postprocess_fn=t5.data.postprocessors.lower_text,
    # We'll use accuracy as our evaluation metric.
    metric_fns=[t5.evaluation.metrics.accuracy],
    # Not required, but helps for mixing and auto-caching.
    num_input_examples=num_nq_examples
)

"""Let's look at a few pre-processed examples from the validation set. Note they contain both the tokenized (integer) and plain-text inputs and targets."""

nq_task = t5.data.TaskRegistry.get("nq_context_free")
ds = nq_task.get_dataset(split="validation", sequence_length={"inputs": 128, "targets": 32})
print("A few preprocessed validation examples...")
for ex in tfds.as_numpy(ds.take(5)):
    print(ex)

"""**Note**: Instead of defining `nq_dataset_fn` and above, we also could have used the `TextLineTask` class with the `parse_tsv` preprocessor for equivalent results as follows:

```py
t5.data.TaskRegistry.add(
    "nq_context_free",
    t5.data.TextLineTask,
    split_to_filepattern=nq_tsv_path,
    text_preprocessor=[
      functools.partial(
          t5.data.preprocessors.parse_tsv,
          field_names=["question", "answer"]),
      trivia_preprocessor
    ],
    postprocess_fn=t5.data.postprocessors.lower_text, 
    metric_fns=[t5.evaluation.metrics.accuracy],
    num_input_examples=num_nq_examples
)
```

## TriviaQA

A second dataset we will use is related to [TriviaQA](https://nlp.cs.washington.edu/triviaqa/). It is also intended for reading comprehension, but, once again, we will modify the task here by ignoring the provided context.

Since the dataset has been imported into [TensorFlow Datasets (TFDS)](https://www.tensorflow.org/datasets/catalog/trivia_qa), we can let it handle the data parsing for us. It will take a few minutes to download and preprocess the first time, but we'll be able to access it instantly from our data directory afterward.
"""

ds = tfds.load(
    "trivia_qa/unfiltered.nocontext",
    data_dir=DATA_DIR,
    # Download data locally for preprocessing to avoid using GCS space.
    download_and_prepare_kwargs={"download_dir": "./downloads"})
print("A few raw validation examples...")
for ex in tfds.as_numpy(ds["validation"].take(2)):
    print(ex)

"""As with Natural Questions, we need to preprocess the raw examples into `inputs` and `targets` features. We can reuse the `trivia_preprocessor` above, but first we need to convert the TriviaQA examples into the correct format, ignoring the fields we don't need for our task.

We'll then define our `Task` and print out a few preprocessed examples from the validation set.

Note that we do not need to specify the splits or number of examples since that information is provided by TFDS.
"""


def tiviaqa_extract_qa(ds):
    def exract_qa(ex):
        return {
            "question": ex["question"],
            "answer": ex["answer"]["value"]
        }

    return ds.map(exract_qa, num_parallel_calls=tf.data.experimental.AUTOTUNE)


t5.data.TaskRegistry.add(
    "triviaqa_context_free",
    # A TfdsTask takes in a TFDS name instead of a tf.data.Dataset function.
    t5.data.TfdsTask,
    tfds_name="trivia_qa/unfiltered.nocontext:1.1.0",
    tfds_data_dir=DATA_DIR,
    sentencepiece_model_path=t5.data.DEFAULT_SPM_PATH,
    text_preprocessor=[tiviaqa_extract_qa, trivia_preprocessor],
    postprocess_fn=t5.data.postprocessors.lower_text,
    metric_fns=[t5.evaluation.metrics.accuracy]
)

# Load and print a few examples.
triviaqa_task = t5.data.TaskRegistry.get("triviaqa_context_free")
ds = triviaqa_task.get_dataset(split="validation", sequence_length={"inputs": 128, "targets": 32})
print("A few preprocessed validation examples...")
for ex in tfds.as_numpy(ds.take(3)):
    print(ex)

"""## Dataset Mixture

We now create a `Mixture` from the above `Tasks`, which we will fine-tune on.

There are different ways to automatically set the rate (for example, based on the number of examples using `rate_num_examples`), but we will just hardcode an equal mixture for simplicity.
"""

t5.data.MixtureRegistry.remove("trivia_all")
t5.data.MixtureRegistry.add(
    "trivia_all",
    ["nq_context_free", "triviaqa_context_free"],
    default_rate=1.0
)

"""# Transferring to new Tasks

We are now ready to fine-tune one of the pre-trained T5 models on our new mixture of closed-book QA tasks.

First, we'll instantiate a `Model` object using the model size of your choice. Note that larger models are slower to train and use but will likely achieve higher accuracy. You also may be able to increase accuracy by training longer with more `FINETUNE_STEPS` below.


## Caveats

* Due to its memory requirements, you will not be able to train the `11B` parameter model on the TPU provided by Colab. Instead, you will need to fine-tune inside of a GCP instance (see [README](https://github.com/google-research/text-to-text-transfer-transformer/)).
* Due to the checkpoint size, you will not be able use the 5GB GCS free tier for the `3B` parameter models. You will need at least 25GB of space, which you can purchase with your $300 of initial credit on GCP.
* While `large` can achieve decent results, it is recommended that you fine-tune at least the `3B` parameter model.

## Define Model
"""

MODEL_SIZE = "3B"  # @param["small", "base", "large", "3B", "11B"]
# Public GCS path for T5 pre-trained model checkpoints
BASE_PRETRAINED_DIR = "gs://t5-data/pretrained_models"
PRETRAINED_DIR = os.path.join(BASE_PRETRAINED_DIR, MODEL_SIZE)
MODEL_DIR = os.path.join(MODELS_DIR, MODEL_SIZE)

if ON_CLOUD and MODEL_SIZE == "3B":
    tf.logging.warn(
        "The `3B` model is too large to use with the 5GB GCS free tier. "
        "Make sure you have at least 25GB on GCS before continuing."
    )
elif ON_CLOUD and MODEL_SIZE == "11B":
    raise ValueError(
        "The `11B` parameter is too large to fine-tune on the `v2-8` TPU "
        "provided by Colab. Please comment out this Error if you're running "
        "on a larger TPU."
    )

# Set parallelism and batch size to fit on v2-8 TPU (if possible).
# Limit number of checkpoints to fit within 5GB (if possible).
model_parallelism, train_batch_size, keep_checkpoint_max = {
    "small": (1, 256, 16),
    "base": (2, 128, 8),
    "large": (8, 64, 4),
    "3B": (8, 16, 1),
    "11B": (8, 16, 1)}[MODEL_SIZE]

tf.io.gfile.makedirs(MODEL_DIR)
# The models from our paper are based on the Mesh Tensorflow Transformer.
model = t5.models.MtfModel(
    model_dir=MODEL_DIR,
    tpu=TPU_ADDRESS,
    tpu_topology=TPU_TOPOLOGY,
    model_parallelism=model_parallelism,
    batch_size=train_batch_size,
    sequence_length={"inputs": 128, "targets": 32},
    learning_rate_schedule=0.003,
    save_checkpoints_steps=5000,
    keep_checkpoint_max=keep_checkpoint_max if ON_CLOUD else None,
    iterations_per_loop=100,
)

"""Before we continue, let's load a [TensorBoard](https://www.tensorflow.org/tensorboard) visualizer so that we can keep monitor our progress. The page should automatically update as fine-tuning and evaluation proceed."""

# Commented out IPython magic to ensure Python compatibility.
if ON_CLOUD:
    #   %reload_ext tensorboard
    import tensorboard as tb
tb.notebook.start("--logdir " + MODELS_DIR)

"""## Fine-tune

We are now ready to fine-tune our model. This will take a while (~2 hours with default settings), so please be patient! The larger the model and more `FINETUNE_STEPS` you use, the longer it will take.

Don't worry, you can always come back later and increase the number of steps, and it will automatically pick up where you left off.
"""

FINETUNE_STEPS = 25000  # @param {type: "integer"}

model.finetune(
    mixture_or_task_name="trivia_all",
    pretrained_model_dir=PRETRAINED_DIR,
    finetune_steps=FINETUNE_STEPS
)

"""## Expected Results [SPOILER ALERT]

Below are the expected accuracies on the Natural Question (NQ) and TriviQA validation sets for various model sizes. The full 11B model produces the exact text of the answer 34.5% and 25.1% of the time on TriviaQA and NQ, respectively. The 3B parameter model, which is the largest that can be trained with a free Cloud TPU in Colab, achieves 29.7% and 23.7%, respectively.

In reality, the model performs better than this since requiring exact match is too strict of a metric, as you’ll see in the examples below. This helps to explain why the model appears to perform better on TriviaQA than NQ, as the latter tends to include more long-form answers extracted from the context.

Please see our [paper on closed-book QA](https://tiny.cc/t5-qa) where achieved even better results.

<img src="https://storage.googleapis.com/t5-data/assets/t5_trivia_expected.png">

## Evaluate

We now evaluate on the validation sets of the tasks in our mixture. Accuracy results will be logged and added to the TensorBoard above.
"""

# Use a larger batch size for evaluation, which requires less memory.
model.batch_size = train_batch_size * 4
model.eval(
    mixture_or_task_name="trivia_all",
    checkpoint_steps="all"
)

"""Let's look at a few random predictions from the validation sets. Note that we measure accuracy based on an *exact match* of the predicted answer and the ground-truth answer. As a result, some of the answers are semantically correct but are counted wrong by the exact match score."""


def print_random_predictions(task_name, n=10):
    """Print n predictions from the validation split of a task."""
    # Grab the dataset for this task.
    ds = t5.data.TaskRegistry.get(task_name).get_dataset(
        split="validation",
        sequence_length={"inputs": 128, "targets": 32},
        shuffle=False)

    def _prediction_file_to_ckpt(path):
        """Extract the global step from a prediction filename."""
        return int(path.split("_")[-2])

    # Grab the paths of all logged predictions.
    prediction_files = tf.io.gfile.glob(
        os.path.join(
            MODEL_DIR,
            "validation_eval/%s_*_predictions" % task_name))
    # Get most recent prediction file by sorting by their step.
    latest_prediction_file = sorted(
        prediction_files, key=_prediction_file_to_ckpt)[-1]

    # Collect (inputs, targets, prediction) from the dataset and predictions file
    results = []
    with tf.io.gfile.GFile(latest_prediction_file) as preds:
        for ex, pred in zip(tfds.as_numpy(ds), preds):
            results.append((tf.compat.as_text(ex["inputs_plaintext"]),
                            tf.compat.as_text(ex["targets_plaintext"]),
                            pred.strip()))

    print("<== Random predictions for %s using checkpoint %s ==>\n" %
          (task_name,
           _prediction_file_to_ckpt(latest_prediction_file)))

    for inp, tgt, pred in random.choices(results, k=10):
        print("Input:", inp)
        print("Target:", tgt)
        print("Prediction:", pred)
        print("Counted as Correct?", tgt == pred)
        print()


print_random_predictions("triviaqa_context_free")
print_random_predictions("nq_context_free")

"""## Predict

Now that we have fine-tuned the model, we can feed T5 arbitrary questions and have it predict the answers!

There is a significant amount of overhead in initializing the model so this may take a few minutes to run each time even though the prediction itself is quite fast.


To avoid this overhead, you might consider exporting a `SavedModel` and running it on [Cloud ML Engine](https://cloud.google.com/ml-engine/).
"""

question_1 = "Where is the Google headquarters located?"  # @param {type:"string"}
question_2 = "What is the most populous country in the world?"  # @param {type:"string"}
question_3 = "Who are the 4 members of The Beatles?"  # @param {type:"string"}
question_4 = "How many teeth do humans have?"  # @param {type:"string"}

questions = [question_1, question_2, question_3, question_4]

now = time.time()
# Write out the supplied questions to text files.
predict_inputs_path = os.path.join(MODEL_DIR, "predict_inputs_%d.txt" % now)
predict_outputs_path = os.path.join(MODEL_DIR, "predict_outputs_%d.txt" % now)
# Manually apply preprocessing by prepending "triviaqa question:".
with tf.io.gfile.GFile(predict_inputs_path, "w") as f:
    for q in questions:
        f.write("trivia question: %s\n" % q.lower())

# Ignore any logging so that we only see the model's answers to the questions.
with tf_verbosity_level('ERROR'):
    model.batch_size = len(questions)
    model.predict(
        input_file=predict_inputs_path,
        output_file=predict_outputs_path,
        # Select the most probable output token at each step.
        temperature=0,
    )

# The output filename will have the checkpoint appended so we glob to get 
# the latest.
prediction_files = sorted(tf.io.gfile.glob(predict_outputs_path + "*"))
print("\nPredictions using checkpoint %s:\n" % prediction_files[-1].split("-")[-1])
with tf.io.gfile.GFile(prediction_files[-1]) as f:
    for q, a in zip(questions, f):
        if q:
            print("Q: " + q)
            print("A: " + a)
            print()

"""# Export Model for Serving

As mentioned in the previous section, exporting a [`SavedModel`](https://www.tensorflow.org/guide/saved_model) can be useful for improving performance during inference or allowing your model to be deployed on a variety of platforms (e.g., TFLite, TensorFlow.js, TensorFlow Serving, or TensorFlow Hub).

## Export SavedModel

We first export the SavedModel. We set a batch size of 1 for simplicity, but it may be more efficient to use a larger batch size if you want to handle multiple requests per call.

For 3B and 11B models the export will take approximately 30-45 minutes.
"""

export_dir = os.path.join(MODEL_DIR, "export")

model.batch_size = 1  # make one prediction per call
saved_model_path = model.export(
    export_dir,
    checkpoint_step=-1,  # use most recent
    beam_size=1,  # no beam search
    temperature=1.0,  # sample according to predicted distribution
)
print("Model saved to:", saved_model_path)

"""## Load SavedModel

One way to test our model is to load it in a TF 1.x `session` so that we can repeatedly predict from the model without the overhead of loading the graph and weights on the TPU each time.

We pay the overhead once here, but it shouldn't take more than a few minutes.
"""

import tensorflow.compat.v1 as tf

tf.reset_default_graph()
sess = tf.Session(TPU_ADDRESS)
meta_graph_def = tf.saved_model.loader.load(sess, ["serve"], saved_model_path)
signature_def = meta_graph_def.signature_def["serving_default"]


def answer(question):
    return sess.run(
        fetches=signature_def.outputs["outputs"].name,
        feed_dict={signature_def.inputs["input"].name: [question]}
    )[0].decode('utf-8')


"""## Predict

We can now call the predict method with different inputs each time and relatively quickly get results.
"""

for question in ["trivia question: where is the google headquarters?",
                 "trivia question: what is the most populous country in the world?",
                 "trivia question: who are the 4 members of the beatles?",
                 "trivia question: how many teeth do humans have?"]:
    print(answer(question))

"""## Deploy SavedModel

You can now deploy your SavedModel for serving (e.g., with [TensorFlow Serving](https://www.tensorflow.org/tfx/tutorials/serving/rest_simple)).
"""