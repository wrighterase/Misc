#!/bin/bash
echo -e "Grabs the ID from an EC2 instace by its tag name\n"
read -p "Instace ID: " instance
aws ec2 describe-instances --filters "Name=tag:Name,Values=$instance" --query 'Reservations[*].Instances[*].InstanceId' --output=text
