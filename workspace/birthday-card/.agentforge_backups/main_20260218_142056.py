# Main Application File for the Birthday Card Application

import logging
import sys


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BirthdayCardApplication:
    def __init__(self):
        self.name = 'Birthday Card Application'
        self.version = '1.0'

    def run(self):
        logging.info(f'{self.name} {self.version} started')
        # Add application logic here
        logging.info(f'{self.name} {self.version} finished')


if __name__ == '__main__':
    try:
        app = BirthdayCardApplication()
        app.run()
    except Exception as e:
        logging.error(f'Error: {e}')
        sys.exit(1)