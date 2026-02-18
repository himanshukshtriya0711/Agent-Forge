# Unit Tests for the Birthday Card Module

from unittest import TestCase
from birthday_card.card import BirthdayCard
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TestBirthdayCard(TestCase):
    def test_init(self):
        recipient_name = 'John Doe'
        sender_name = 'Jane Doe'
        birthday_date = '2022-01-01'
        card = BirthdayCard(recipient_name, sender_name, birthday_date)
        self.assertEqual(card.recipient_name, recipient_name)
        self.assertEqual(card.sender_name, sender_name)
        self.assertEqual(card.birthday_date, birthday_date)

    def test_customization(self):
        recipient_name = 'John Doe'
        sender_name = 'Jane Doe'
        birthday_date = '2022-01-01'
        card = BirthdayCard(recipient_name, sender_name, birthday_date)
        # Add customization logic here
        # self.assertEqual(card.customization, 'customization')

if __name__ == '__main__':
    logging.info('Running unit tests for the birthday card module')
    import unittest
    unittest.main()