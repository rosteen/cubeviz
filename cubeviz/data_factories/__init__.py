# Licensed under a 3-clause BSD style license - see LICENSE.rst
from .jwst import read_jwst_data_cube
from .kmos import read_kmos_data_cube
from .manga import read_manga_data_cube
from glue.core import Data
from glue.core.coordinates import coordinates_from_header
from ..listener import CUBEVIZ_LAYOUT
from ..layout import FLUX, ERROR, MASK

from os.path import basename, splitext
import yaml
import os
import glob
import logging
from astropy.io import fits
import numpy as np
from glue.config import data_factory

logging.basicConfig()
logger = logging.getLogger('cubeviz_data_configuration')

DEFAULT_DATA_CONFIGS = os.path.join(os.path.dirname(__file__), 'configurations')
CUBEVIZ_DATA_CONFIGS = 'CUBEVIZ_DATA_CONFIGS'

class DataConfiguration:
    """
    This class is used to parse a YAML configuration file.

    """

    def __init__(self, config_file):
        """
        Given the configuration file, save it and grab the name and priority
        :param config_file:
        """
        self._config_file = config_file

        with open(self._config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)

            self._name = cfg['name']
            self._type = cfg['type']

            try:
                self._priority = int(cfg.get('priority', 0))
            except:
                self._priority = 0

            self._configuration = cfg['match']

            self._data = cfg.get('data', None)

    def load_data(self, data_filename):
        """
        Load the data based on the extensions defined in the matching YAML file.  THen
        create the datacube and return it.

        :param data_filename:
        :return:
        """
        hdulist = fits.open(data_filename)

        print(hdulist)

        try:
            flux_index = int(self._data['FLUX'])
        except:
            flux_index = self._data['FLUX']

        flux = hdulist[flux_index]
        flux_data = flux.data

        try:
            error_index = int(self._data['ERROR'])
        except:
            error_index = self._data['ERROR']
        var_data = hdulist[error_index].data

        if not self._data['DQ'] == 'None':
            mask_data = hdulist[self._data['DQ']].data
        else:
            mask_data = np.empty(flux_data.shape)

        label = "{}: {}".format(self._name, splitext(basename(data_filename))[0])

        data = Data(label=label)

        data.coords = coordinates_from_header(flux.header)
        data.meta[CUBEVIZ_LAYOUT] = self._name

        data.add_component(component=flux_data, label=FLUX)
        data.add_component(component=var_data, label=ERROR)
        data.add_component(component=mask_data, label=MASK)

        return data

    def matches(self, filename):
        """
        Main call to which we pass in the file to see if it matches based
        on the criteria in the config file.

        :param filename:
        :return:
        """
        self._fits = fits.open(filename)


        # Now call the internal processing.
        matches = self._process('all', self._configuration['all'])

        if matches:
            return True
        else:
            return False

    def _process(self, key, conditional):
        """
        Internal processing. This will get called numerous times recursively.

        :param key: The type of check we want to do
        :param conditional: The thing we are checking
        :return:
        """

        if 'all' == key:
            return self._all(conditional)
        elif 'any' == key:
            return self._any(conditional)
        elif 'equal' == key:
            return self._equal(conditional)
        elif 'startswith' == key:
            return self._startswith(conditional)
        elif 'extension_name' == key:
            return self._exists(conditional)

    #
    # Branch processing
    #

    def _all(self, conditionals):
        """
        Check all the conditionals and they must all be true for this to return true.

        :param conditionals:
        :return:
        """
        for key, conditional in conditionals.items():
            ret = self._process(key, conditional)
            if not ret:
                return False
        return True

    def _any(self, conditionals):
        """
        Check each conditional and return true for the first one that matches true. Else return False

        :param conditionals:
        :return:
        """

        for key, conditional in conditionals.items():
            # process conditional
            ret = self._process(key, conditional)
            if ret:
                return ret

        return False

    #
    # Leaf processing
    #

    def _equal(self, value):
        """
        This is to check if a header_key entry has the same value as what is passed in here.

        :param value:
        :return:
        """
        return self._fits[0].header.get(value['header_key'], False) == value['value']

    def _startswith(self, value):
        """
        This is to check if a header_key entry starts with the value as what is passed in here.

        :param value:
        :return:
        """
        return self._fits[0].header.get(value['header_key'], '').startswith(value['value'])

    def _extension_name(self, value):
        """
        This is to check if a header_key entry has the same value as what is passed in here.

        :param value:
        :return:
        """
        return value in self._fits



class DataFactoryConfiguration:
    """
    This class takes in lists of files or directories that are or contain data configuration YAML files. These
    can come from:
       1. the default location
       2. from the command line "--data-configs <file-or-directory>"
       3. from the environment variable CUBEVIZ_DATA_CONFIGS=<files-or-directories>
    """

    def _find_yaml_files(self, files_or_directories):
        """
        Given the files_or_directories, create a list of all relevant YAML files.

        :param files_or_directories:
        :return:
        """
        config_files = []

        # If the thing passed in was a string then we'll split on colon. If there is only one
        # directory then it will create a list anyway.
        if isinstance(files_or_directories, str):
            files_or_directories = files_or_directories.split(':')

        for x in files_or_directories:
            if os.path.exists(x):
                # file, just append
                if os.path.isfile(x):
                    config_files.append(x)
                # directory, find all yaml under it.
                else:
                    files  = glob.glob(os.path.join(x, '*.yaml'))
                    config_files.extend(files)

        return config_files


    def __init__(self, in_configs):
        """
        The IFC takes either a directory (that contains YAML files), a list of directories (each of which contain
        YAML files) or a list of YAML files.  Each YAML file defines requirements

        :param in_configs: Directory, list of directories, or list of files.
        """

        self._config_files = []

        # Get all the available YAML data configuration files based on the command line.
        logger.debug('YAML data configuration fiels from command line: {}'.format(in_configs))
        self._config_files.extend(self._find_yaml_files(in_configs))

        # Get all the available YAML data configuration files based on the environment variable.
        if CUBEVIZ_DATA_CONFIGS in os.environ:
            logger.debug('YAML data configuration fiels from environment variable: {}'.format(os.environ[CUBEVIZ_DATA_CONFIGS]))
            self._config_files.extend(self._find_yaml_files(os.environ[CUBEVIZ_DATA_CONFIGS]))

        # Get all the available YAML data configuration files based on the default directory
        logger.debug(
            'YAML data configuration fiels from the default directory: {}'.format(DEFAULT_DATA_CONFIGS))
        self._config_files.extend(self._find_yaml_files(DEFAULT_DATA_CONFIGS))

        logger.debug(
            'YAML data configuration files: {}'.format('\n'.join(self._config_files)))

        for config_file in self._config_files:

            # Load the YAML file and get the name, priority and create the data factory wrapper
            with open(config_file, 'r') as yamlfile:
                cfg = yaml.load(yamlfile)

            name = cfg['name']

            try:
                priority = int(cfg.get('priority', 0))
            except:
                priority = 0

            dc = DataConfiguration(config_file)
            wrapper = data_factory(name, dc.matches, priority=priority)
            wrapper(dc.load_data)
