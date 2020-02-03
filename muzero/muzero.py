from muzero.muzero_config import MuZeroConfig, MuZeroBoardConfig, MuZeroAtariConfig
from muzero.network_storage import NetworkStorage
from muzero.replay_buffer import ReplayBuffer
from muzero.network import Network
from mcts.tree import Tree
from environement.games import Game

from tensorflow.keras.optimizers import Optimizer, SGD
import tensorflow as tf

"""
The class representing the entire MuZero structure. 
Separates the process of generating training data from the actual "playing" in order to avoid chasing a moving target.
The network structure consists of three separate models: Representation Model, Dynamics Model and the Prediction Model.
Each training period starts with a new network, which is trained on training data "improved" on each generation period.
"""


class MuZero(object):

    def __init__(self, config: MuZeroConfig):
        self.network_storage = NetworkStorage()  # Storage containing all saved networks
        self.replay_buffer = ReplayBuffer(config)  # The replay buffer containing the matches to train on
        self.config = config  # Configuration file

    """
    Use the most recent version of the network to generate the trainings data and save it into the replay buffer
    """

    def populate_replay_buffer(self):
        network = self.network_storage.latest_network()
        for match in range(self.config.window_size):
            game = self.play_game(network)
            self.replay_buffer.save_game(game)

    """
        Reset environment and repeatedly choose an action based on the Monte Carlo Tree Search till the game is over
        """

    def play_game(self, network: Network) -> Game:
        game = self.config.new_game()
        tree = Tree(action_list=game.legal_actions(),
                    config=self.config,
                    network=network,
                    player_list=game.players,
                    discount=self.config.discount)

        while not game.terminal() and len(game.history) < self.config.max_moves:
            image = game.make_image(0)
            value, reward, policy_logits, hidden_state = network.initial_inference(image)

            tree.reset(value=value, reward=reward, policy_logits=policy_logits, hidden_state=hidden_state)
            action = tree.get_action(evaluation=False)

            game.apply(action)
            game.store_search_statistics(tree.root)
        return game

    """
    Create a new network and train it on the data generated by the self-play
    """

    def train_network(self):
        # Create new network (representation model, dynamics model, prediction model)
        network = Network()
        # Set the learning rate accordingly to the current training step
        learning_rate = self.config.lr_init * self.config.lr_decay_rate ** (
                tf.compat.v1.train.get_global_step() / self.config.lr_decay_steps)
        # Optimizer is the SGD optimizer with momentum
        optimizer = SGD(learning_rate, self.config.momentum)

        for step in range(self.config.training_steps):
            # Save the current state of the network oon
            if step % self.config.checkpoint_interval == 0:
                self.network_storage.save_network(step, network)

            # Sample a batch from the replay buffer
            batch = self.replay_buffer.sample_batch(self.config.num_unroll_steps, self.config.td_steps)

            # Calculate the loss that results from the batch and update the weights accordingly
            self.update_weights(optimizer, network, batch, self.config.weight_decay)

        # Finally save the trained network
        self.network_storage.save_network(self.config.training_steps, network)

    """
    First predict the values for the given observations and actions 
    Then calculate the loss between those predictions and results of the MCTS stored in the replay buffer 
    Before optimizing the weights, add a L2-Regularization to the loss (adds a penalty if the weights get to big; prevents overfitting)
    Finally updating all weights in the network (all 3 models) with the given optimizer.
    """

    def update_weights(self, optimizer: Optimizer, network: Network, batch, weight_decay: float):
        loss = 0
        for image, actions, targets in batch:
            # Transform real observation to hidden state, then predict value, reward and policy distribution for it
            # TODO: Dont understand how the reward can be predicted on a single state (without any given action)
            value, reward, policy_logits, hidden_state = network.initial_inference(image)
            predictions = [(1.0, value, reward, policy_logits)]

            # Recurrent steps, from action and previous hidden state.
            for action in actions:
                value, reward, policy_logits, hidden_state = network.recurrent_inference(hidden_state, action)
                hidden_state = scale_gradient(hidden_state, 0.5)
                predictions.append((1.0 / len(actions), value, reward, policy_logits))

            # Calculate the loss between the predictions and the target
            for prediction, target in zip(predictions, targets):
                gradient_scale, value, reward, policy_logits = prediction
                target_value, target_reward, target_policy = target

                l = (
                        self.scalar_loss(value, target_value) +
                        self.scalar_loss(reward, target_reward) +
                        tf.nn.softmax_cross_entropy_with_logits(logits=policy_logits, labels=target_policy)
                )

                loss += scale_gradient(l, gradient_scale)

        # Add L2-Regularization to the overall loss
        for weights in network.get_weights():
            loss += weight_decay * tf.nn.l2_loss(weights)

        # Optimize the current weights
        optimizer.minimize(loss, network.get_weights())

    """
    Calculating the scalar loss between prediction and the target and returning it as a tensor.
    MSE in board games
    TODO: Finish cross entropy for atari games with categorical values 
    """

    def scalar_loss(self, prediction, target) -> float:
        if isinstance(self.config, MuZeroBoardConfig):
            squared_error = tf.keras.losses.MSE(prediction, target)
            return squared_error

        elif isinstance(self.config, MuZeroAtariConfig):
            raise Exception('MuZero', 'Loss for AtariConfig is not implemented yet')
        else:
            raise Exception('MuZero', 'Please use the AtariConfig or the BoardConfig for calculating appropriate loss')

    def evaluate(self):
        pass


def scale_gradient(tensor, scale):
    return tensor * scale + tf.stop_gradient(tensor) * (1 - scale)
