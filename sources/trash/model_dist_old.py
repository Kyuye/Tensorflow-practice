
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
from tensorflow.contrib.learn.python.learn.preprocessing import VocabularyProcessor

import collections
import numpy as np
import pandas
import json
import csv
import os
import time
from pprint import pprint

FLAGS = tf.flags.FLAGS
tf.flags.DEFINE_integer("vocabulary_size", 50000, "vocabulary size")
tf.flags.DEFINE_integer("max_document_length", 150, "max document(sentence) length")
# tf.flags.DEFINE_string("train_data", "gs://wgan/dataset/twitter_emotion_v2(p,n,N).csv", "train data path")
# tf.flags.DEFINE_string("train_data", "./DataSet/twitter_emotion_v2(p,n,N).csv", "train data path")
tf.flags.DEFINE_string("train_data", "/dataset/twitter_emotion_v2(p,n,N).csv", "train data path")
tf.flags.DEFINE_integer("batch_size", 10, "batch size for training")
tf.flags.DEFINE_integer("regularizer_scale", 0.9, "reguarizer scale")
tf.flags.DEFINE_integer("embed_dim", 50, "embedding dimension")
tf.flags.DEFINE_integer("g_hidden1", 50, "g function 1st hidden layer unit")
tf.flags.DEFINE_integer("g_hidden2", 50, "g function 1st hidden layer unit")
tf.flags.DEFINE_integer("g_hidden3", 50, "g function 1st hidden layer unit")
tf.flags.DEFINE_integer("g_logits", 50, "g function logits")
tf.flags.DEFINE_integer("f_hidden1", 50, "f function 1st hidden layer unit")
tf.flags.DEFINE_integer("f_hidden2", 50, "f function 2nd hidden layer unit")
tf.flags.DEFINE_integer("f_logits", 50, "f function logits")
tf.flags.DEFINE_integer("emotion_class", 3, "number of emotion classes")
tf.flags.DEFINE_integer("memory_size", 50, "LSTM cell(memory) size")
tf.flags.DEFINE_string("log_dir", "./logs/", "path to logs directory")


class WasserstienGAN(object):
    def __init__(self, clip_values=(-0.01, 0.01), critic_iterations=5):
        self.batch_steps = 0
        self.critic_iterations = critic_iterations
        self.clip_values = clip_values
        self.max_document_length = FLAGS.max_document_length
        self.object_pairs_set = []
        self.max_object_pairs_num = 0
        print("reading data..")
        self.data = self.read_datafile(os.getcwd() + FLAGS.train_data)
        print("words identifing")
        self.word_ids  = self.word_identify(self.data)
        print("building pair set...")
        self.object_pairs_set = self.build_pair_set(self.word_ids)
        print("embedding...")
        self.object_pairs = self.embedding_object_pairs(self.object_pairs_set)
        print("one hot encoding ....")
        self.label = self.one_hot_encoding(self.data)
        print("session opening...")
        self.open_session()
        print("session opened")



    def build_generated_pair_set(self, gen_data):
        generated_pair_set = []
        for seq in tf.unstack(gen_data):
            comb = [i for i in range(FLAGS.max_document_length)]
            ids = []
            while len(comb) > 2:
                ids += list(map(lambda x: [comb[0], x], comb))[1:]
                del comb[0]
            
            pair = tf.nn.embedding_lookup(seq, ids)
            generated_pair_set.append(tf.concat([pair[:,0], pair[:,1]], axis=1))
            
        return tf.stack(generated_pair_set)


    def one_hot_encoding(self, dataframe):
        indices = []
        for s in dataframe["Sentiment"]:
            if s == "Neg":
                indices.append(0)
            elif s == "neutral":
                indices.append(1)
            elif s == "Pos":
                indices.append(2)
            else:
                indices.append(0)
            
        return tf.one_hot(indices=indices, depth=3, on_value=1.0, off_value=0.0)


    def build_pair_set(self, word_ids):
        object_pairs_set = []
        self.max_object_pairs_num = 0
        for ids in word_ids:
            object_pairs = []
            seq = ids.tolist()
            seq_length = np.count_nonzero(ids)
            while seq_length >= 2:
                object_pairs += list(map(lambda x: (seq[0], x), seq[:seq_length]))[1:]
                del seq[0]
                seq_length = np.count_nonzero(seq)

            object_pairs_set.append(object_pairs)

            if self.max_object_pairs_num < len(object_pairs):
                self.max_object_pairs_num = len(object_pairs)

        return object_pairs_set
    
    def embedding_object_pairs(self, object_pairs_set):
        embed_reuse = False
        object_pairs_list = []
        for ids in object_pairs_set:
            object_pairs_embed = tf.contrib.layers.embed_sequence(
                ids=ids,
                vocab_size=FLAGS.vocabulary_size,
                embed_dim=FLAGS.embed_dim,
                reuse=embed_reuse,
                scope="embeddings")
            
            object_pairs_concat = tf.reshape(
                object_pairs_embed,
                shape=(-1, 2*FLAGS.embed_dim))
            
            object_pairs_list.append(tf.pad(
                tensor=object_pairs_concat,
                paddings=[
                    [0, self.max_object_pairs_num-len(ids)], 
                    [0, 0]])
            )
            embed_reuse = True

        return tf.stack(object_pairs_list)


    def get_batch(self, train, label, minibatch_size, fullbatch_size):
        train_batch = train[self.batch_steps%fullbatch_size*minibatch_size:(self.batch_steps%fullbatch_size+1)*minibatch_size]
        label_batch = label[self.batch_steps%fullbatch_size*minibatch_size:(self.batch_steps%fullbatch_size+1)*minibatch_size]
        return train_batch, label_batch

        
    def read_datafile(self, filename):
        print(os.getcwd())
        data = pandas.read_csv(filename, usecols=["Sentiment", "content"], nrows=100)
        data = data[data["content"] != "0"]
        data["content"] = data["content"].astype("str")
        return data


    def word_identify(self, dataframe):
        contents = dataframe["content"].values.tolist()
        vocab_processor = VocabularyProcessor(self.max_document_length)
        word_ids = np.array(list(vocab_processor.fit_transform(contents)))
        self.vocabulary_size = np.max(word_ids)
        return word_ids


    def _generator(self, x):
        with tf.variable_scope("generator") as scope:
            rnn_cell = tf.contrib.rnn.BasicLSTMCell(num_units=FLAGS.memory_size)
            out, _ = tf.contrib.rnn.static_rnn(cell=rnn_cell, inputs=x, dtype=tf.float32)
            Wo = tf.Variable(tf.truncated_normal(shape=(len(x), FLAGS.memory_size, FLAGS.embed_dim)))
            bo = tf.Variable(tf.zeros(shape=(len(x), FLAGS.embed_dim)))
            return tf.unstack(tf.matmul(out, Wo), axis=1)+ bo

    def _create_generator(self, samples):
        self.z = tf.unstack(
            tf.random_uniform(
                shape=(samples, self.max_document_length, FLAGS.embed_dim), 
                minval=-1, 
                maxval=1, 
                dtype=tf.float32), 
                axis=1)
        self.gen_data = self._generator(self.z)


    def _discriminator(self, x, reuse=False):
        with tf.variable_scope("discriminator") as scope:
            gs = []
            g_reuse = reuse
            f_reuse = reuse
            for i in range(self.max_object_pairs_num):
                g_in = tf.reshape(x[:,i,:], (-1, 2*FLAGS.embed_dim))
                g_layer1 = tf.layers.dense(
                    inputs=g_in,
                    units=FLAGS.g_hidden1,
                    activation=tf.nn.relu,
                    use_bias=True,
                    kernel_initializer=tf.truncated_normal_initializer(),
                    bias_initializer=tf.zeros_initializer(),
                    kernel_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    bias_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    activity_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    trainable=True,
                    name="g_layer1",
                    reuse=g_reuse
                )

                g_layer2 = tf.layers.dense(
                    inputs=g_layer1,
                    units=FLAGS.g_hidden2,
                    activation=tf.nn.relu,
                    use_bias=True,
                    kernel_initializer=tf.truncated_normal_initializer(),
                    bias_initializer=tf.zeros_initializer(),
                    kernel_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    bias_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    activity_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    trainable=True,
                    reuse=g_reuse,
                    name="g_layer2"
                )

                g_layer3 = tf.layers.dense(
                    inputs=g_layer2,
                    units=FLAGS.g_hidden3,
                    activation=tf.nn.relu,
                    use_bias=True,
                    kernel_initializer=tf.truncated_normal_initializer(),
                    bias_initializer=tf.zeros_initializer(),
                    kernel_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    bias_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    activity_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    trainable=True,
                    reuse=g_reuse,
                    name="g_layer3"
                )

                g_out = tf.layers.dense(
                    inputs=g_layer3,
                    units=FLAGS.g_logits,
                    activation=tf.nn.relu,
                    use_bias=True,
                    kernel_initializer=tf.truncated_normal_initializer(),
                    bias_initializer=tf.zeros_initializer(),
                    kernel_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    bias_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    activity_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                    trainable=True,
                    reuse=g_reuse,
                    name="g_out"
                )

                gs.append(g_out)
                g_reuse=True

            
            g_batch = tf.reduce_sum(tf.transpose(tf.stack(gs), [1, 0, 2]), axis=1)

            f_layer1 = tf.layers.dense(
                inputs=g_batch,
                units=FLAGS.f_hidden1,
                activation=tf.nn.relu,
                use_bias=True,
                kernel_initializer=tf.truncated_normal_initializer(),
                bias_initializer=tf.zeros_initializer(),
                kernel_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                bias_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                activity_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                trainable=True,
                reuse=f_reuse,
                name="f_layer1"
            )

            f_layer2 = tf.layers.dense(
                inputs=f_layer1,
                units=FLAGS.f_hidden2,
                activation=tf.nn.relu,
                use_bias=True,
                kernel_initializer=tf.truncated_normal_initializer(),
                bias_initializer=tf.zeros_initializer(),
                kernel_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                bias_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                activity_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                trainable=True,
                reuse=f_reuse,
                name="f_layer2"
            )

            logits = tf.layers.dense(
                inputs=f_layer2,
                units=FLAGS.f_logits,
                activation=tf.nn.relu,
                use_bias=True,
                kernel_initializer=tf.truncated_normal_initializer(),
                bias_initializer=tf.zeros_initializer(),
                kernel_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                bias_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                activity_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                trainable=True,
                reuse=f_reuse,
                name="f_out"
            )
        
            supervised_logits = tf.layers.dense(
                inputs=logits, 
                units=FLAGS.emotion_class,
                activation=None,
                use_bias=True,
                kernel_initializer=tf.truncated_normal_initializer(),
                bias_initializer=tf.zeros_initializer(),
                kernel_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                bias_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                activity_regularizer=tf.contrib.layers.l2_regularizer(FLAGS.regularizer_scale),
                trainable=True,
                reuse=f_reuse,
                name="supervised_layer"
                )

        return logits, supervised_logits


    def _gan_loss(self, logits_real, logits_fake, supervised_logits, label, use_features=False):
        supervised_loss = tf.losses.softmax_cross_entropy(label, supervised_logits)
        discriminator_loss = tf.reduce_mean(logits_real - logits_fake) + supervised_loss
        gen_loss = tf.reduce_mean(logits_fake)
        return discriminator_loss, gen_loss


    def _create_network(self, optimizer="Adam", learning_rate=2e-4, optimizer_param=0.9):
        print("Setting up model...")
        real_pairs, labels = self.get_batch(self.object_pairs, self.label, FLAGS.batch_size, 100)
        print("create generator...")
        self._create_generator(FLAGS.batch_size)
        print("building generated pair set...")
        fake_pairs = self.build_generated_pair_set(self.gen_data)

        print("building discriminator for real data...")
        logits_real, logits_supervised = self._discriminator(real_pairs, reuse=False)
        print("building discriminator for fake data...")
        logits_fake, _ = self._discriminator(fake_pairs, reuse=True)

        # Loss calculation
        print("building gan loss graph...")
        self.discriminator_loss, self.gen_loss = self._gan_loss(logits_real, logits_fake, logits_supervised, labels)

        print("variables scoping...")
        train_variables = tf.trainable_variables()

        self.generator_variables = [v for v in train_variables if v.name.startswith("generator")]
        self.discriminator_variables = [v for v in train_variables if v.name.startswith("discriminator")]

        # print(list(map(lambda x: x.op.name, self.generator_variables)))
        # print(list(map(lambda x: x.op.name, self.discriminator_variables)))

        self.saver = tf.train.Saver(self.generator_variables)

        optim = self._get_optimizer(optimizer, learning_rate, optimizer_param)

        print("building train op")
        self.generator_train_op = self._train(self.gen_loss, self.generator_variables, optim)
        self.discriminator_train_op = self._train(self.discriminator_loss, self.discriminator_variables, optim)


    def initialize_network(self, mode):
        print("initialize")
        if mode == 'train':
            print("train mode")
            print(self.job_name)
            if self.job_name == "ps":
                print("ps work")
                self.server.join()
            elif self.job_name == "worker":
                print("workers work")
                with tf.device(tf.train.replica_device_setter()):
                    print("building network")
                    self._create_network()
                    print("variables initializing")
                    self.sess.run(tf.global_variables_initializer())
                print("training...")
                self.train_model(100)
                print("session closed")
        elif mode == 'predict':
            print("building network")
            self._create_generator()
            print("session opening...")
            self.open_session()
            print("predict..")
            self.predict()
            print("session closed")
            self.sess.close()
        else:
            print("please select the mode train/predict")
            return


    def _get_optimizer(self, optimizer_name, learning_rate, optimizer_param):
        self.learning_rate = learning_rate
        if optimizer_name == "Adam":
            return tf.train.AdamOptimizer(learning_rate, beta1=optimizer_param)
        elif optimizer_name == "RMSProp":
            return tf.train.RMSPropOptimizer(learning_rate, decay=optimizer_param)
        else:
            raise ValueError("Unknown optimizer %s" % optimizer_name)

    def _train(self, loss_val, var_list, optimizer):
        self.batch_steps+=1
        grads = optimizer.compute_gradients(loss_val, var_list=var_list)
        return optimizer.apply_gradients(grads, global_step=self.global_step)

    def predict(self):
        saver = tf.train.Saver()
        saver.restore(self.sess, "./CheckPoint/rnn_GAN")
        tf.train.write_graph(self.sess.graph_def,"./CheckPoint/",'graph.pbtxt',False)
        _pred  = self.sess.run(tf.transpose(self.gen_data, perm=[1,0,2]))
        print(_pred)


    def train_model(self, max_iterations):
        print("Training Wasserstein GAN model...")
        clip_discriminator_var_op = [var.assign(tf.clip_by_value(var, self.clip_values[0], self.clip_values[1])) for
                                        var in self.discriminator_variables]

        itr = 0
        while not self.sess.should_stop():    
            print("iterations: ", itr)
            if itr < 25 or itr % 500 == 0:
                critic_itrs = 25
            else:
                critic_itrs = self.critic_iterations

            for critic_itr in range(critic_itrs):
                self.sess.run(self.discriminator_train_op)
                self.sess.run(clip_discriminator_var_op)

            self.sess.run(self.generator_train_op)

            if itr % 200 == 0:
                d_loss_val, g_loss_val = self.sess.run([self.discriminator_loss, self.gen_loss])
                self.saver.save(self.sess, "./logs")
                print("Step: %d, generator loss: %g, discriminator_loss: %g" % (itr, g_loss_val, d_loss_val))

            
            itr += 1

            if i > max_iterations:
                break



    # def train_model(self):
    #     print("training Wasserstein GAN model....")
    #     clip_discriminator_var_op = [var.assign(tf.clip_by_value(var, self.clip_values[0], self.clip_values[1])) for
    #     var in self.discriminator_variables]

    #     while not self.sess.should_stop():
    #         print("start training")
    #         def set_critic_fn(cond):
    #             print("set critic")
    #             if cond == True:
    #                 self.critic_itrs=25
    #             else:
    #                 self.critic_itrs=self.critic_iterations


    #         set_critic_itr = tf.cond(
    #             tf.logical_or(
    #                 self.global_step < 25, 
    #                 tf.mod(self.global_step, 500)),
    #             true_fn=lambda x: set_critic_fn(True),
    #             false_fn=lambda x: set_critic_fn(False))

    #         self.i = tf.constant(0)
    #         b = lambda i: tf.add(i, 1)

    #         def body():
    #             self.sess.run(self.discriminator_train_op)
    #             self.sess.run(clip_discriminator_var_op)
    #             self.i = tf.add(self.i, 1)
    #             print("training in body ")


    #         cond = lambda i: tf.less(i, self.critic_itrs)
    #         loop_critic = tf.while_loop(cond, body, [i])


    #         self.sess.run(set_critic_itr)
    #         self.sess.run(loop_critic)
    #         print("discriminator updated")


    #         self.sess.run(self.generator_train_op)
    #         print("generator updated")
            

    # def train_model(self, max_iterations):
    #     print("Training Wasserstein GAN model...")
    #     clip_discriminator_var_op = [var.assign(tf.clip_by_value(var, self.clip_values[0], self.clip_values[1])) for
    #                                     var in self.discriminator_variables]


    #     for itr in range(1, max_iterations):
    #         print("iterations: ", itr)
    #         if itr < 25 or itr % 500 == 0:
    #             critic_itrs = 25
    #         else:
    #             critic_itrs = self.critic_iterations

    #         for critic_itr in range(critic_itrs):
    #             self.sess.run(self.discriminator_train_op)
    #             self.sess.run(clip_discriminator_var_op)

    #         self.sess.run(self.generator_train_op)

    #         if itr % 200 == 0:
    #             g_loss_val, d_loss_val = self.sess.run([self.gen_loss, self.discriminator_loss])
    #             self.saver.save(self.sess, "./CheckPoint/rnn_GAN")
    #             print("Step: %d, generator loss: %g, discriminator_loss: %g" % (itr, g_loss_val, d_loss_val))



    def close_session(self):
        self.coord.request_stop()
        self.coord.join(self.thread)
        self.sess.close()
        
    def open_session(self):
        self.global_step = tf.contrib.framework.get_or_create_global_step()
        tf_config = os.environ.get("TF_CONFIG")
        tf_config_json = json.loads(tf_config)

        self.cluster = tf_config_json.get("cluster")
        self.job_name = tf_config_json.get("task", {}).get("type")
        self.task_index = tf_config_json.get("task", {}).get("index")

        self.cluster_spec = tf.train.ClusterSpec(self.cluster)
        
        pprint(tf_config_json)

        self.server = tf.train.Server(self.cluster_spec, job_name=self.job_name,task_index=self.task_index)

        print("open session")
        hooks = [tf.train.StopAtStepHook(last_step=100)]
        self.sess = tf.train.MonitoredTrainingSession(
            master=self.server.target,
            is_chief=(self.task_index == 0),
            checkpoint_dir=FLAGS.log_dir,
            hooks=hooks)
        self.coord = tf.train.Coordinator()
        self.thread = tf.train.start_queue_runners(self.sess, self.coord)
        print("train ready")

def main(argv=None):
    gan = WasserstienGAN(critic_iterations=5)
    print("train start")
    gan.initialize_network("train")


if __name__ == "__main__":
    if not os.path.exists('./dataset/twitter_emotion_v2(p,n,N).csv'):
        print("before file exist: ", os.path.exists('./dataset/twitter_emotion_v2(p,n,N).csv'))
        if not os.path.isdir('dataset'):
            print("dir exist: ", os.path.isdir('dataset'))
            os.mkdir('dataset')
        os.system("gsutil -m cp gs://wgan/dataset/* $(pwd)/dataset/")
        print("after file exist: ", os.path.exists('./dataset/twitter_emotion_v2(p,n,N).csv'))
    print("data set copy")

    # print("sleep...")
    # print(os.getcwd())
    # time.sleep(10)
    print("start!!")

    tf.app.run()
