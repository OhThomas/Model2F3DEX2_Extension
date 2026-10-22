# Runs Model2F3DEX2 and fixes vertice coloring, FA commands, links meshes, and copies output to clipboard
# while providing features like environmental sheen, transparency, backface culling, etc.

# TODO: - uniform command arguments
#       - end command based on command given (like with D9 to flip the bits)
#       - make file paths relative
#       - make costume apply to different parts, preferably with unique palette pointers
#       - rename fa_com/fa_loc variables

# Copyright (C) 2025 Thomas Rader

import pyclip
import os
import subprocess
import argparse
import binascii
import re

parser = argparse.ArgumentParser()
parser.add_argument("-file","--file","-obj_file","--obj_file",required=True,type=str,help="OBJ file we're converting.")
parser.add_argument("-offset","--offset","-location","--location",default="80400000",type=str,help="Hexadecimal location of where we're adding the file (as a string, ex: '0x80750000').")
parser.add_argument("-model2f3dex_path","--model2f3dex_path","-model2f3dex_ssb","--model2f3dex_ssb",default="",type=str,help="Location of Model2F3DEX-SSB.exe (include exe).")
parser.add_argument("-palette_costume","--palette_costume","-costume","--costume",default="",help="Changes FD1 (palette) command with DE000000 0EXXXXXX to make palette based on costume palette. Enter entire DE command, ex DE0000000E000000.")
parser.add_argument("-backface_culling","--backface_culling",default="",help="Adds backface culling with D9FFFBFF 00000000, and adding D9FFFFFF 00000400 afterwards. Enter 'all' or which parts will receive the culling seperated by commas, ex: '0,2,3,4'")
parser.add_argument("-sheen","--sheen","-env_sheen","--env_sheen",default="",help="Adds environmental sheen with sheen_command. Enter 'all' or which parts will receive the sheen seperated by commas, ex: '0,2,3,4'")
parser.add_argument("-trans","--trans","-transparency","--transparency",default="",help="Adds transparency to texture. Enter 'all' or which parts will receive the transparency seperated by commas, ex: '0,2,3,4'")
parser.add_argument("-sheen_command","--sheen_command","-env_sheen_command","--env_sheen_command","-shine","--shine",default="D9FFFFFF00040001,F54004000001066C,D700000207FF07FF",help="Commands to replace to apply sheen with (first 3 digits determine command, comma seperated). Default is D9FFFFFF00040001,F54004000001066C,D700000207FF07FF")
parser.add_argument("-trans_command","--trans_command","-transparency_command","--transparency_command",default="E300100100008000,FCFFFFFFFFFCF279,E200001C00507078",help="Commands to replace to apply shine with (first 3 digits determine command, comma seperated). Default is D9FFFFFF00040001,F54004000001066C,D700000207FF07FF")
parser.add_argument("-no_mtl","--no_mtl",action="store_true",help="Doesn't change Ka/Kd commands in mtl file (Ka blocks Kd command for Model2F3DEX2-SSB which is needed for primitive coloring).")
parser.add_argument("-debug","--debug",action="store_true",help="Prints debugging messages.")
parser.add_argument("-no_copy","--no_copy",action="store_true",help="Doesn't copy output to clipboard.")
parser.add_argument("-o","--o","-output","--output",default="m2f3_output.bin",type=str,help="Output file.")

args = parser.parse_args()

# Setting variables
file_path = args.file
offset = args.offset
model2f3dex_path = args.model2f3dex_path
output_path = args.o
fa_pattern = "FA000000000000FF"
df_pattern = "DF00000000000000"
e7_pattern = "E700000000000000"
palette_regex = re.compile(r'FD[1][0-8]000080[0-9,A-F]{6}')
costume_regex = re.compile(r'DE0000000E[0-9,A-F]{6}')
ram_pointer_regex = re.compile(r'[0,D,F][1,D,E][0-9,A-F]{6}80[0-9,A-F]{6}')
jump_regex = re.compile(r'DE0[0,1]000080[0-9,A-F]{6}')
de_or_df_regex = re.compile(r"D[E,F]0[0,1]0000[0,8]0[0-9,A-F]{6}")
d9_regex = re.compile(r'D9[0-9,A-F]')
backface_command = "D9FFFBFF00000000"
backface_end_command = "D9FFFFFF00000400"
sheen_end_command = "D9FBFFFF00000000"

# Converts linear to sRGB
def lin_to_srgb(l):
    return 12.92 * l if l <= 0.0031308 else 1.055 * l ** (1 / 2.4) - 0.055

# Converts Kd command to sRGB from MTL file
def fix_kd(line):
    srgb_string = "#srgb"
    parts = line.split()
    if parts and parts[0] == "Kd" and parts[-1] != srgb_string:
        r, g, b = (lin_to_srgb(float(x)) for x in parts[1:4])
        return f"Kd {r:.6f} {g:.6f} {b:.6f} {srgb_string}\n"
    return line

def mtl_change(file_path):
    """
    Removes Ka commands and modifies Kd commands to be sRGB in an MTL file for primitive coloring.
    Only removes Ka commands that are followed by a Kd command.

    Args:
        file_path (str): Source file.

    Returns:
        (none)
    """
    lines = []
    temp_file = file_path+"temp"
    current_ka_loc = 0
    ka_regex = re.compile(r'^Ka .*')
    kd_regex = re.compile(r'^Kd .*')

    # Going through MTL file
    try:
        with open(file_path, "rb") as fr, open(temp_file, "wb") as fw:
            while True:
                offset = fr.tell()
                line = fr.readline()
                if not line:
                    break

                # Checking if Ka command found to record lines to replace with if Kd found
                if ka_regex.match(line.decode()):
                    current_ka_loc = offset
                    lines = []

                # If Kd found then we go back to last Ka command found and write everything but it
                if kd_regex.match(line.decode()) and len(lines) <= 1:
                    if args.debug:
                        print(f"kd found at line {line.decode()}")
                    fw.seek(current_ka_loc)
                    line = str(fix_kd(line.decode())).encode()
                    if args.debug:
                        print(f"kd conversion = {line.decode()}")

                # Writing to new file
                fw.write(line)
                lines.append(line)
            fw.truncate()
        os.replace(temp_file,file_path)
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
    except ValueError:
        print(f"Error: Invalid hex location '{offset}'")
    return None

# Creating full paths and removing output if it exists
# TODO: make file paths relative
try:
    # Get the current working directory
    current_directory = os.getcwd()

    # Construct full paths for source and destination
    source_path = os.path.join(current_directory, file_path)
    destination_path = os.path.join(current_directory, output_path)

    # Setting up path to Model2F3DEX2
    if model2f3dex_path == "":
        current_file_path = os.path.abspath(__file__)
        current_file_directory = os.path.dirname(current_file_path)
        model2f3dex_path = current_file_directory + "\\Model2F3DEX2.exe"

    if os.path.exists(destination_path):
        os.remove(destination_path)
        print(f"File '{destination_path}' deleted.")

    if not args.no_mtl:
        mtl_path = os.path.splitext(source_path)[0] + ".mtl"
        mtl_change(mtl_path)
except FileNotFoundError as e:
    print(f"{e}")
    exit(1)
except Exception as e:
    print(f"An error occurred: {e}")
    exit(1)

# Reads hexadecimal data from a file with hex offset given
def read_hex_from_offset(file_path, offset, num_bytes=8):
    """
    Reads data from binary file.

    Args:
        file_path (str): Source file.
        offset (str): Where in the file to read the data from.
        num_bytes (int): How many bytes to read.

    Returns:
        str: Hexadecimal data read from binary file.
    """
    try:
        with open(file_path, "rb") as f:
            offset_decimal = int(offset, 16)
            f.seek(offset_decimal)
            data = f.read(num_bytes)
            #print(f"Data read at {offset}: {data.hex()}")
            return data.hex()
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
    except ValueError:
        print(f"Error: Invalid hex location '{offset}'")
    return None

# Writes hexadecimal data to a file with hex offset given
def write_hex_from_offset(new_file_path, offset, hex_string):
    """
    Writes over data in binary file.

    Args:
        new_file_path (str): File to write to.
        offset (str): Where to write the data to.
        hex_string (str): Hexadecimal data we are writing.

    Returns:
        None
    """
    try:
        with open(new_file_path, "rb+") as f:
            offset_decimal = int(offset, 16)
            f.seek(offset_decimal)
            binary_data = binascii.unhexlify(hex_string)
            f.write(binary_data)
            #print(f"Data written at {offset}: {hex_string} as {binary_data}")
    except FileNotFoundError:
        print(f"Error: File not found at {new_file_path}")
    except ValueError:
        print(f"Error: Invalid hex location '{offset}', hex string is {hex_string}")
    except binascii.Error as e:
        print(f"Error converting hex string: {e}. Ensure the hex string has an even number of characters and contains only valid hex digits (0-9, A-F).")

# Appends hexadecimal data to a file with hex offset given
def append_hex_from_offset(new_file_path, offset, hex_string):
    """
    Appends data to binary file.

    Args:
        new_file_path (str): File to write to.
        offset (str): Where to append the data to.
        hex_string (str): Hexadecimal data we are appending.

    Returns:
        None
    """
    try:
        with open(new_file_path, "r+b") as f:
            offset_decimal = int(offset, 16)
            f.seek(offset_decimal)
            remaining_data = f.read()
            f.seek(offset_decimal)
            binary_data = hex_string#binascii.unhexlify(hex_string)
            f.write(binary_data)
            f.write(remaining_data)
            #print(f"Data written at {offset}: {hex_string} as {binary_data}")
    except FileNotFoundError:
        print(f"Error: File not found at {new_file_path}")
    except ValueError as e:
        print(f"Error: Invalid hex location '{offset}' '{e}'")
    except binascii.Error as e:
        print(f"Error converting hex string: {e}. Ensure the hex string has an even number of characters and contains only valid hex digits (0-9, A-F).")

def update_pointer_data(file_path=destination_path, offset="0x0", amount="0x0", num_bytes=8):
    """
    Updates pointer data by adding amount to any pointer past offset

    Args:
        file_path (str): Source file.
        offset (str): Where the change occurs so the pointers past this point get updated.
        amount (int): How much to add.
        num_bytes (int): How many bytes to be processing. 

    Returns:
        str: Hex location of first FA command; returns -1 if nothing found.
    """
    # Setting variables
    file_size = int(os.path.getsize(file_path))
    data_loc = hex(0)
    data_loc,data_com = find_pattern(destination_path,data_loc,e7_pattern)
    while data_com != -1:
        data_loc = hex(int(data_loc, 16) + 8)
        # Setting decimal value to make sure we don't read over file size
        data_loc_dec = int(data_loc,16)

        # Finding any pointer pattern in file
        data_loc,data_com = find_pattern(destination_path,data_loc,ram_pointer_regex,True)
        if data_com == -1:
            break
        if data_com == df_pattern:
            break
        pointer = data_com[-8:]

        # Printing pointer debug
        if args.debug:
            print(f"pointer = {pointer} offset = {offset} amount to add = {amount}")

        # Updating pointers if they're more than our offset
        if int(pointer,16) >= int(offset,16):
            pointer = '{:04x}'.format(int(pointer,16)+int(amount,16))
            new_command = str(data_com[:8] + pointer).upper()
            if args.debug:
                print(f"pointer = {pointer} new_command {new_command}")
            write_hex_from_offset(destination_path,data_loc,new_command)
            print(f"{data_loc}: changing from {data_com} to {new_command}")

        # No more to read, exiting
        if data_loc_dec >= file_size:
            return data_loc, -1

# Finds pattern in a f3dex model file and returns it and its location in the file
def find_pattern(file_path=file_path, reading_loc="0x0", pattern="", break_on_df=False, ending_pattern=""):
    """
    Finds pattern location in f3dex model file.

    Args:
        file_path (str): Source file.
        reading_loc (str): Where to start looking.
        pattern (str): What we're looking for

    Returns:
        str: Hex location of pattern command; returns -1 if nothing found.
    """
    # Setting variables
    file_size = int(os.path.getsize(file_path))
    reading_loc_hex = hex(int(reading_loc, 16))
    data = read_hex_from_offset(file_path, reading_loc_hex, 8)

    while 1:
        # Setting decimal value to make sure we don't read over file size
        reading_loc_dec = int(reading_loc_hex,16)

        # Debug statement showing pattern data
        if args.debug:
            print(f"{reading_loc_hex}: data = {data} pattern = {pattern}")

        # Checking if the pattern is regex or string
        if isinstance(pattern, re.Pattern):
            # Checking if pattern matches
            if pattern.match(str(data).upper()):
                # Checking if DF is not final DF command
                if str(data).upper() == "DF00000000000000":
                    if reading_loc_dec+9 <= file_size:
                        return reading_loc_hex,"DF00000000000000"
                return hex(int(reading_loc_hex, 16)), str(data).upper()
            # Checking if the ending_pattern is regex or string
            if isinstance(ending_pattern, re.Pattern):
                # Checking if end_pattern matches
                if ending_pattern.match(str(data).upper()):
                    return reading_loc_hex, -1
            else:
                if str(data).upper() == ending_pattern.upper():
                    return reading_loc_hex, -1
        else:
            # Checking if pattern matches
            if str(data).upper() == pattern.upper():
                # Checking if DF is not final DF command
                if str(data).upper() == "DF00000000000000":
                    if reading_loc_dec+9 <= file_size:
                        return reading_loc_hex,"DF00000000000000"
                return hex(int(reading_loc_hex, 16)), str(data).upper()
            # Checking if the ending_pattern is regex or string
            if isinstance(ending_pattern, re.Pattern):
                # Checking if end_pattern matches
                if ending_pattern.match(str(data).upper()):
                    return reading_loc_hex, -1
            else:
                if str(data).upper() == ending_pattern.upper():
                    return reading_loc_hex, -1

        # Always break on df if set
        if break_on_df:
            if str(data).upper() == "DF00000000000000":
                return hex(int(reading_loc_hex, 16)), str(data).upper()

        # No more to read, exiting
        if reading_loc_dec >= file_size:
            print("Couldn't find indexes, exiting.")
            return reading_loc_hex, -1

        # Reading next 8 bytes
        reading_loc = hex(int(reading_loc, 16) + 8)
        reading_loc_hex = hex(int(reading_loc,16))
        data = read_hex_from_offset(file_path, reading_loc_hex, 8)
    return -1

def d9_check(command,old_command):
    """
    Checks if a previous command is a D9 command and will AND(&) the first half of bits
    and OR(|) the second half of bits with the current command if so.

    Args:
        command (str): New command we're going to be placing in the file.
        old_command (str): Previous command to check if it's a D9 command.

    Returns:
        str: D9 command that's either combined with the old command or just the new one.
    """
    if d9_regex.match(str.upper(command[:3])):
        d9_current_msb = old_command[8:]
        d9_com_msb = command[8:]
        d9_current_lsb = old_command[2:8]
        d9_com_lsb = command[2:8]
        d9_new_msb = "{:08x}".format(int(d9_current_msb,16) | int(d9_com_msb,16))
        d9_new_lsb = "{:06x}".format(int(d9_current_lsb,16) & int(d9_com_lsb,16))
        command = "D9"+d9_new_lsb+d9_new_msb
        print(f"d9_msb = {d9_new_msb} d9_lsb = {d9_new_lsb} command = {command}")
    return command

def command_list_check(parts_number,parts_list,command_list,fa_loc,loc_offset): 
    """
    Goes through a specific section of the file we're modifying, that is the part we want
    to add commands to, and then checks if those commands already exist (overwrites if so)
    and appends them if they don't while updating pointers.

    Args:
        parts_number (int): Current part to check in the file.
        parts_list (list of str): Entire list of parts that will be modified with these commands.
        command_list (list of str): List of commands that we're adding/appending.
        fa_loc (str): Hex value of current location in the file we're modifying.
        loc_offset(str): fa_loc + offset of the RAM address we're adding this file to.

    Returns:
        str: D9 command that's either combined with the old command or just the new one.
    """
    if str(parts_number) in parts_list or parts_list[0] == "all":
        for command in command_list:
            command_regex_amount = 0 # Use this to change how much of a command we look for in regex, ex: FC(color) command = 2; FD5(palette) = 3

            # Change regex depending on command, FC = 2; FD5 = 3, etc
            if command[:2] == "FC":
                command_regex_amount = 1
            command_reg = command[:3-command_regex_amount]
            command_reg = re.compile(re.escape(command_reg)+r'[0-9,A-F]'+rf'{{{13+command_regex_amount}}}')
            command_loc,command_com = find_pattern(destination_path,fa_loc,command_reg,True,de_or_df_regex)

            # Printing command search debug statement
            if args.debug:
                print(f"command_reg = {command_reg} command = {command} command_loc = {command_loc} command_com = {command_com}")

            # Appending the command if it's not already set or and end match pattern, overwrite if otherwise
            if not de_or_df_regex.match(str(command_com).upper()) and command_com != -1:
                command = d9_check(command,command_com)
                write_hex_from_offset(destination_path,command_loc,command)
            else:
                append_hex_from_offset(destination_path,fa_loc,binascii.unhexlify(command))
                update_pointer_data(destination_path,loc_offset,"0x8","0x8")

def add_command(destination_path,parts_list,beginning_pattern,ending_pattern,command_list=[],end_command_list=[]):
    """
    Adds command and updates pointer offsets. Adds command after 
    beginning_pattern and end_command before ending_pattern in parts_list given
    (for each part that gets the command like with sheen or backface_culling, ex: 0,2,3).

    Args:
        destination_path (str): Source file.
        parts_list (str): Comma seperated integers representing which parts get the commands.
        beginning_pattern (str): Where we add command.
        ending_pattern (str): Where we add end_command, all we add to the part.
        command (str): What we add.
        end_command (str): What we add to end the command with.

    Returns:
        (none)

    TODO: 
        - update_pointer_data needs the hex amount of what command we're adding incase
          we add things bigger than 0x8. 
        - make no end_command function
    """
    # Setting variables
    if parts_list != "":
        parts_number = 0
        parts_list = parts_list.split(',')
        fa_com = ""
        fa_loc = "0x0"
        fa_loc,fa_com = find_pattern(destination_path,fa_loc,beginning_pattern)
        while fa_com != -1:
            fa_loc = hex(int(fa_loc, 16) + 8)
            loc_offset = hex(int(fa_loc,16) + int(args.offset,16))

            # Adding the command
            command_list_check(parts_number,parts_list,command_list,fa_loc,loc_offset)

            # Going to ending command
            fa_loc,fa_com = find_pattern(destination_path,fa_loc,ending_pattern)
            loc_offset = hex(int(fa_loc,16) + int(args.offset,16))

            # If we're at the end of the file, we want to add the end command before the DF command
            if fa_com == -1:
                fa_loc = hex(int(fa_loc, 16) - 8)

            # Checking if D9 command is already added at the end (NEED TO DO THIS WITH EVERY COMMAND THAT NEEDS TO BE RESET)
            d9_loc_check = hex(int(fa_loc, 16) - 8)
            d9_loc_check = read_hex_from_offset(destination_path,d9_loc_check)
            if d9_regex.match(str(d9_loc_check).upper()):
                fa_loc = hex(int(fa_loc, 16) - 8)

            # Adding the end command
            command_list_check(parts_number,parts_list,end_command_list,fa_loc,loc_offset)
            if fa_com == -1:
                break
            
            # Finding next command location
            fa_loc = hex(int(fa_loc, 16) + 8)
            fa_loc,fa_com = find_pattern(destination_path,fa_loc,beginning_pattern)
            parts_number = parts_number + 1

def get_commands(destination_path,parts_list,beginning_pattern,ending_pattern,command=""):
    """
    Returns command and location of a command pattern you give within a certain part model of the file.

    Args:
        destination_path (str): Source file.
        parts_list (list of str): Comma seperated integers representing which parts to look for the commands.
        beginning_pattern (str): Where we add command.
        ending_pattern (str): Where we add end_command, all we add to the part.
        command (str): What we're looking for.

    Returns:
        (list of str,str): Locations of the commands found; The command found from pattern.
    """
    # Setting variables
    return_list = []
    if parts_list != "":
        parts_number = 0
        parts_list = parts_list.split(',')
        fa_com = ""
        fa_loc = "0x0"
        fa_loc,fa_com = find_pattern(destination_path,fa_loc,beginning_pattern)
        while fa_com != -1:
            fa_loc = hex(int(fa_loc, 16) + 8)

            # Looking for the command
            command_loc,command_com = find_pattern(destination_path,fa_loc,command,True,de_or_df_regex)

            # If the command is found then we add it to our list
            if command_com != -1:
                if str(parts_number) in parts_list or parts_list[0] == "all":
                    return_list.append([command_loc,command_com])
            
            # Going to ending command
            fa_loc,fa_com = find_pattern(destination_path,fa_loc,ending_pattern)

            if fa_com == -1:
                break
            
            # Finding next command location
            fa_loc = hex(int(fa_loc, 16) + 8)
            fa_loc,fa_com = find_pattern(destination_path,fa_loc,beginning_pattern)
            parts_number = parts_number + 1
    return return_list

# Running Model2F3DEX2
objs = f'ObjFile="{source_path}",{offset},false,false,"{output_path}"'
arguments = [objs]
command = [model2f3dex_path] + arguments

output = ""
# Running process
try:
    command = model2f3dex_path+" "+objs
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Looping process output
    while True:
        output_line = process.stdout.readline()
        output = output + output_line
        if output_line.replace('\n','').replace('\r','') == "Press any key to exit.":
            break
        if not output_line:
            break
    # process.wait() # Ensure the process has finished
    process.kill()

except Exception as e:
    # Printing result
    print(f"{e}")
    exit(1)

# Printing result
print(f"output: \n{output}")

# Replacing FA commands
fa_com = ""
fa_loc = "0x0"
fa_loc,fa_com = find_pattern(destination_path,fa_loc,fa_pattern)
while fa_com != -1:
    print(f"{fa_loc}: changing from FA000000 000000FF to FA000000 FFFFFFFF")
    write_hex_from_offset(destination_path,fa_loc,"FA000000FFFFFFFF")
    # Finding FA command location
    fa_loc = hex(int(fa_loc, 16) + 8)
    fa_loc,fa_com = find_pattern(destination_path,fa_loc,fa_pattern)

# Replacing DF commands
fa_com = ""
fa_loc = "0x0"
fa_loc,fa_com = find_pattern(destination_path,fa_loc,df_pattern)
# Searching for more DF commands, we jump to next mesh part if so (replace last DF with DE01)
while fa_com != -1:
    if fa_com == df_pattern:
        last_loc = fa_loc
        fa_loc = hex(int(fa_loc, 16) + 8)
        fa_loc,fa_com = find_pattern(destination_path,fa_loc,e7_pattern)
        if fa_com == -1:
            break
        # If here then we need to replace last DF command
        overwrite = int(last_loc,16)
        offset_decimal = int(offset, 16)
        write_to_offset = offset_decimal + int(fa_loc,16)
        write_to_offset = '{:08x}'.format(write_to_offset)
        write_to_offset = "DE010000"+write_to_offset
        print(f"{hex(overwrite)}: changing from DF000000 00000000 to {write_to_offset}")
        write_hex_from_offset(destination_path,hex(overwrite),write_to_offset)

    # Finding next DF command location
    fa_loc = hex(int(fa_loc, 16) + 8)
    fa_loc,fa_com = find_pattern(destination_path,fa_loc,df_pattern)

# Replacing FD1 commands
if args.palette_costume != "":
    # Setting palette_costume to default if not set properly
    if not costume_regex.match(args.palette_costume):
        args.palette_costume = "DE0000000E000000"

    # Replacing
    fa_com = ""
    fa_loc = "0x0"
    fa_loc,fa_com = find_pattern(destination_path,fa_loc,palette_regex)
    while fa_com != -1:
        # Output for what we're replacing
        read_com = read_hex_from_offset(destination_path,fa_loc)
        print(f"{fa_loc}: changing from {read_com} to {args.palette_costume}")

        write_hex_from_offset(destination_path,fa_loc,args.palette_costume)

        # Finding next command location
        fa_loc = hex(int(fa_loc, 16) + 8)
        fa_loc,fa_com = find_pattern(destination_path,fa_loc,palette_regex)

# Adding backface culling
add_command(destination_path,args.backface_culling,e7_pattern,jump_regex,[backface_command],[backface_end_command])

# Adding environmental sheen
sheen_list = args.sheen_command.split(',')
add_command(destination_path,args.sheen,e7_pattern,jump_regex,sheen_list,[sheen_end_command])

# Adding transparency
trans_list = args.trans_command.split(',')
add_command(destination_path,args.trans,e7_pattern,jump_regex,trans_list,[])
trans_palettes = get_commands(destination_path,args.trans,e7_pattern,jump_regex,palette_regex)
if args.debug and trans_palettes:
    print(f"trans_palettes = {str(trans_palettes)}")
# Changing first palette in all palettes we want to be transparent to 0000 (transparent)
for trans_palette in trans_palettes:
    palette_address = trans_palette[1][-8:]
    palette_address = int(palette_address,16) - int(args.offset,16)
    write_hex_from_offset(destination_path,hex(palette_address),"0000")

# Copying hex data to clipboard
if not args.no_copy:
    # Read binary data from new file
    binary_data = ""
    try:
        with open(destination_path, 'rb') as f:
            binary_data = f.read()
            binary_data = binary_data.hex()
    except FileNotFoundError:
        print("Couldn't copy hex data to clipboard.")
        exit(1)

    # Copying to clipboard
    pyclip.copy(binary_data) # copy data to the clipboard
    print(f"Coping data from new file {os.path.basename(destination_path)} to clipboard.")