import unittest
from datetime import datetime
from birthday_card.main import BirthdayCard


class TestBirthdayCard(unittest.TestCase):
    def test_birthday_message(self):
        # Arrange
        name = 'John Doe'
        birthdate = '1990-01-01'
        card = BirthdayCard(name, birthdate)
        
        # Act
        message = card.generate_message()
        
        # Assert
        self.assertIsNotNone(message)
        self.assertIn(name, message)
        
    def test_invalid_birthdate(self):
        # Arrange
        name = 'John Doe'
        birthdate = 'invalid'
        
        # Act and Assert
        with self.assertRaises(ValueError):
            BirthdayCard(name, birthdate)
        
if __name__ == '__main__':
    unittest.main()